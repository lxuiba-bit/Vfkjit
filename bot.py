import logging
import sqlite3
import asyncio
import time
import json
from datetime import datetime
import io
from PyPDF2 import PdfReader

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from groq import Groq
from openai import OpenAI
from serpapi import GoogleSearch

from config import TELEGRAM_BOT_TOKEN, GROQ_API_KEY, OPENAI_API_KEY, ADMIN_IDS, DEFAULT_SYSTEM_PROMPT, DB_NAME, RATE_LIMIT_SECONDS, API_TIMEOUT, MAX_HISTORY_LENGTH, AI_PROVIDER, GROQ_MODEL_NAME, OPENAI_MODEL_NAME, SERPAPI_API_KEY

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize AI clients
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
openai_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Database setup
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            system_prompt TEXT DEFAULT ?, 
            blocked BOOLEAN DEFAULT 0,
            current_model TEXT DEFAULT ?,
            is_premium BOOLEAN DEFAULT 0,
            message_count INTEGER DEFAULT 0
        )
    """, (DEFAULT_SYSTEM_PROMPT, AI_PROVIDER))
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role TEXT,
            content TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """
    )
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT,
            user_id INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            data TEXT
        )
    """
    )
    conn.commit()
    conn.close()

# User management functions
def get_user_data(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user_data = cursor.fetchone()
    conn.close()
    return user_data

def create_or_update_user(user_id, username, first_name, last_name):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)",
                   (user_id, username, first_name, last_name))
    conn.commit()
    conn.close()

def is_user_blocked(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT blocked FROM users WHERE user_id = ?", (user_id,))
    blocked = cursor.fetchone()
    conn.close()
    return blocked[0] if blocked else False

def set_user_blocked(user_id, blocked_status):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET blocked = ? WHERE user_id = ?", (blocked_status, user_id))
    conn.commit()
    conn.close()

def is_user_premium(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT is_premium FROM users WHERE user_id = ?", (user_id,))
    premium = cursor.fetchone()
    conn.close()
    return premium[0] if premium else False

def set_user_premium(user_id, premium_status):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_premium = ? WHERE user_id = ?", (premium_status, user_id))
    conn.commit()
    conn.close()

def increment_message_count(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET message_count = message_count + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_message_count(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT message_count FROM users WHERE user_id = ?", (user_id,))
    count = cursor.fetchone()
    conn.close()
    return count[0] if count else 0

# Conversation history functions
def add_message_to_history(user_id, role, content):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO conversations (user_id, role, content) VALUES (?, ?, ?)",
                   (user_id, role, content))
    conn.commit()
    conn.close()

def get_conversation_history(user_id, limit=MAX_HISTORY_LENGTH):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM conversations WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?",
                   (user_id, limit))
    history = cursor.fetchall()
    conn.close()
    return [{"role": role, "content": content} for role, content in reversed(history)]

def clear_conversation_history(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_user_system_prompt(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT system_prompt FROM users WHERE user_id = ?", (user_id,))
    prompt = cursor.fetchone()
    conn.close()
    return prompt[0] if prompt else DEFAULT_SYSTEM_PROMPT

def set_user_system_prompt(user_id, new_prompt):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET system_prompt = ? WHERE user_id = ?", (new_prompt, user_id))
    conn.commit()
    conn.close()

def get_user_ai_model(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT current_model FROM users WHERE user_id = ?", (user_id,))
    model = cursor.fetchone()
    conn.close()
    return model[0] if model else AI_PROVIDER

def set_user_ai_model(user_id, new_model):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET current_model = ? WHERE user_id = ?", (new_model, user_id))
    conn.commit()
    conn.close()

# Analytics functions
def log_event(event_type, user_id, data=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO analytics (event_type, user_id, data) VALUES (?, ?, ?)",
                   (event_type, user_id, json.dumps(data) if data else None))
    conn.commit()
    conn.close()

# Rate limiting
last_message_time = {}

async def rate_limit_middleware(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in last_message_time and (time.time() - last_message_time[user_id]) < RATE_LIMIT_SECONDS:
        await update.message.reply_text("Please wait a moment before sending another message.")
        return False
    last_message_time[user_id] = time.time()
    return True

# Admin check decorator
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in ADMIN_IDS:
            await update.message.reply_text("You are not authorized to use this command.")
            return
        return await func(update, context)
    return wrapper

# Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    create_or_update_user(user.id, user.username, user.first_name, user.last_name)
    log_event("start_command", user.id)
    await update.message.reply_html(
        f"Hi {user.mention_html()}! I am your AI assistant. How can I help you today?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Reset Chat", callback_data="reset_chat")],
            [InlineKeyboardButton("Set Personality", callback_data="set_personality")],
            [InlineKeyboardButton("Change AI Model", callback_data="change_ai_model")]
        ])
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "Here are the commands you can use:\n"
        "/start - Start the bot and get a welcome message.\n"
        "/help - Show this help message.\n"
        "/ask <your question> - Ask the AI a question.\n"
        "/set_prompt <new prompt> - Set a custom system prompt for the AI.\n"
        "/get_prompt - View your current system prompt.\n"
        "/forget - Clear the current conversation history.\n"
        "/model <groq|openai> - Change the AI model to use.\n"
        "/premium - Check your premium status.\n"
        "/web_search <query> - Search the web for information (Premium feature).\n"
        "/generate_image <prompt> - Generate an image from text (Premium feature).\n"
        "/summarize <text> - Summarize given text (Premium feature).\n"
        "/stats - (Admin) Show bot statistics.\n"
        "/broadcast <message> - (Admin) Send a message to all users.\n"
        "/ban <user_id> - (Admin) Ban a user.\n"
        "/unban <user_id> - (Admin) Unban a user.\n"
        "/set_premium <user_id> <0|1> - (Admin) Set user premium status.\n"
    )
    await update.message.reply_text(help_text)

async def ask_ai(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await rate_limit_middleware(update, context): return

    user_id = update.effective_user.id
    if is_user_blocked(user_id):
        await update.message.reply_text("You are blocked from using this bot.")
        return

    # Basic message limit for non-premium users
    if not is_user_premium(user_id) and get_message_count(user_id) >= 50: # Example limit
        await update.message.reply_text("You have reached your message limit. Upgrade to premium for unlimited access!")
        return

    user_message = update.message.text
    if user_message.startswith("/ask"):
        user_message = user_message[len("/ask"):].strip()

    if not user_message:
        await update.message.reply_text("Please provide a message to the AI.")
        return

    await update.message.reply_chat_action("typing")

    add_message_to_history(user_id, "user", user_message)
    conversation_history = get_conversation_history(user_id)
    system_prompt = get_user_system_prompt(user_id)
    current_model_provider = get_user_ai_model(user_id)

    messages = [{"role": "system", "content": system_prompt}] + conversation_history

    try:
        if current_model_provider == "groq" and groq_client:
            chat_completion = groq_client.chat.completions.create(
                messages=messages,
                model=GROQ_MODEL_NAME,
                temperature=0.7,
                timeout=API_TIMEOUT
            )
            ai_response = chat_completion.choices[0].message.content
        elif current_model_provider == "openai" and openai_client:
            chat_completion = openai_client.chat.completions.create(
                messages=messages,
                model=OPENAI_MODEL_NAME,
                temperature=0.7,
                timeout=API_TIMEOUT
            )
            ai_response = chat_completion.choices[0].message.content
        else:
            await update.message.reply_text("AI model not configured or invalid. Please use /model to select a valid model.")
            return

        add_message_to_history(user_id, "assistant", ai_response)
        increment_message_count(user_id)
        log_event("ai_message", user_id, {"model": current_model_provider, "prompt": user_message, "response": ai_response})
        await update.message.reply_text(ai_response)
    except Exception as e:
        logger.error(f"Error communicating with AI API ({current_model_provider}): {e}")
        log_event("ai_error", user_id, {"model": current_model_provider, "error": str(e)})
        await update.message.reply_text("Sorry, I\\\\'m having trouble connecting to the AI right now. Please try again later.")

async def set_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    new_prompt = " ".join(context.args)
    if not new_prompt:
        await update.message.reply_text("Please provide a new system prompt. Example: /set_prompt You are a sarcastic assistant.")
        return
    set_user_system_prompt(user_id, new_prompt)
    log_event("set_prompt", user_id, {"new_prompt": new_prompt})
    await update.message.reply_text(f"Your system prompt has been updated to: \n`{new_prompt}`")

async def get_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    current_prompt = get_user_system_prompt(user_id)
    await update.message.reply_text(f"Your current system prompt is: \n`{current_prompt}`")

async def forget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    clear_conversation_history(user_id)
    log_event("forget_command", user_id)
    await update.message.reply_text("Your conversation history has been cleared.")

async def change_ai_model_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not context.args or context.args[0].lower() not in ["groq", "openai"]:
        await update.message.reply_text("Usage: /model <groq|openai>")
        return
    new_model = context.args[0].lower()
    if new_model == "groq" and not groq_client:
        await update.message.reply_text("Groq API key is not configured.")
        return
    if new_model == "openai" and not openai_client:
        await update.message.reply_text("OpenAI API key is not configured.")
        return
    set_user_ai_model(user_id, new_model)
    log_event("change_model", user_id, {"new_model": new_model})
    await update.message.reply_text(f"Your AI model has been set to: `{new_model}`")

async def premium_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    status = "Premium" if is_user_premium(user_id) else "Standard"
    message_count = get_message_count(user_id)
    await update.message.reply_text(f"Your account status: {status}\nMessages sent: {message_count}")

@admin_only
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM conversations")
    total_messages = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_premium = 1")
    premium_users = cursor.fetchone()[0]
    cursor.execute("SELECT event_type, COUNT(*) FROM analytics GROUP BY event_type")
    event_counts = cursor.fetchall()
    conn.close()

    stats_text = f"Total Users: {total_users}\nPremium Users: {premium_users}\nTotal AI Messages: {total_messages}\n\nEvent Counts:\n"
    for event_type, count in event_counts:
        stats_text += f"- {event_type}: {count}\n"
    
    await update.message.reply_text(stats_text)
    log_event("admin_stats", update.effective_user.id)

@admin_only
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message_to_send = " ".join(context.args)
    if not message_to_send:
        await update.message.reply_text("Please provide a message to broadcast.")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE blocked = 0")
    users = cursor.fetchall()
    conn.close()

    sent_count = 0
    for user_id_tuple in users:
        user_id = user_id_tuple[0]
        try:
            await context.bot.send_message(chat_id=user_id, text=message_to_send)
            sent_count += 1
            await asyncio.sleep(0.1) # Small delay to avoid hitting Telegram API limits
        except Exception as e:
            logger.warning(f"Could not send broadcast message to user {user_id}: {e}")
    log_event("admin_broadcast", update.effective_user.id, {"message": message_to_send, "sent_to": sent_count})
    await update.message.reply_text(f"Broadcast complete. Sent to {sent_count} users.")

@admin_only
async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /ban <user_id>")
        return
    user_id_to_ban = int(context.args[0])
    set_user_blocked(user_id_to_ban, True)
    log_event("admin_ban", update.effective_user.id, {"banned_user_id": user_id_to_ban})
    await update.message.reply_text(f"User {user_id_to_ban} has been banned.")

@admin_only
async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /unban <user_id>")
        return
    user_id_to_unban = int(context.args[0])
    set_user_blocked(user_id_to_unban, False)
    log_event("admin_unban", update.effective_user.id, {"unbanned_user_id": user_id_to_unban})
    await update.message.reply_text(f"User {user_id_to_unban} has been unbanned.")

@admin_only
async def set_premium(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 2 or not context.args[0].isdigit() or context.args[1] not in ["0", "1"]:
        await update.message.reply_text("Usage: /set_premium <user_id> <0|1>")
        return
    user_id = int(context.args[0])
    status = bool(int(context.args[1]))
    set_user_premium(user_id, status)
    log_event("admin_set_premium", update.effective_user.id, {"target_user_id": user_id, "status": status})
    await update.message.reply_text(f"User {user_id} premium status set to {status}.")

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "reset_chat":
        await forget(query, context)
    elif query.data == "set_personality":
        await query.edit_message_text(
            "Please use /set_prompt <new prompt> to change my personality. Example: /set_prompt You are a helpful coding assistant."
        )
    elif query.data == "change_ai_model":
        keyboard = [
            [InlineKeyboardButton("Groq", callback_data="model_groq")],
            [InlineKeyboardButton("OpenAI", callback_data="model_openai")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Choose your AI model:", reply_markup=reply_markup)
    elif query.data.startswith("model_"):
        new_model = query.data.split("_")[1]
        user_id = query.from_user.id
        if new_model == "groq" and not groq_client:
            await query.edit_message_text("Groq API key is not configured.")
            return
        if new_model == "openai" and not openai_client:
            await query.edit_message_text("OpenAI API key is not configured.")
            return
        set_user_ai_model(user_id, new_model)
        log_event("change_model_button", user_id, {"new_model": new_model})
        await query.edit_message_text(f"Your AI model has been set to: `{new_model}`")

async def web_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_user_premium(user_id):
        await update.message.reply_text("Web search is a premium feature. Please upgrade to use it.")
        log_event("premium_feature_denied", user_id, {"feature": "web_search"})
        return

    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("Please provide a search query. Usage: /web_search <query>")
        return

    if not SERPAPI_API_KEY:
        await update.message.reply_text("SerpApi key is not configured. Please contact the administrator.")
        return

    await update.message.reply_chat_action("typing")
    await update.message.reply_text(f"Searching the web for \'{query}\'...")

    try:
        search = GoogleSearch({
            "q": query,
            "api_key": SERPAPI_API_KEY
        })
        results = search.get_dict()
        organic_results = results.get("organic_results", [])

        if organic_results:
            response_text = "Here are some search results:\n\n"
            for i, result in enumerate(organic_results[:5]): # Limit to top 5 results
                title = result.get("title")
                link = result.get("link")
                snippet = result.get("snippet")
                response_text += f"{i+1}. [{title}]({link})\n{snippet}\n\n"
            await update.message.reply_text(response_text, parse_mode="Markdown")
            log_event("web_search_success", user_id, {"query": query, "results_count": len(organic_results)})
        else:
            await update.message.reply_text("No search results found for your query.")
            log_event("web_search_no_results", user_id, {"query": query})

    except Exception as e:
        logger.error(f"Error during web search: {e}")
        log_event("web_search_error", user_id, {"query": query, "error": str(e)})
        await update.message.reply_text("Sorry, I encountered an error while performing the web search. Please try again later.")

async def voice_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_user_premium(user_id):
        await update.message.reply_text("Voice message processing is a premium feature. Please upgrade to use it.")
        log_event("premium_feature_denied", user_id, {"feature": "voice_message"})
        return

    if not openai_client:
        await update.message.reply_text("OpenAI API key is not configured for voice processing. Please contact the administrator.")
        return

    file_id = update.message.voice.file_id
    new_file = await context.bot.get_file(file_id)
    file_buffer = io.BytesIO()
    await new_file.download_to_memory(file_buffer)
    file_buffer.name = "voice_message.ogg" # OpenAI Whisper expects a filename

    await update.message.reply_chat_action("typing")
    await update.message.reply_text("Transcribing your voice message...")

    try:
        transcript = openai_client.audio.transcriptions.create(
            model="whisper-1", 
            file=file_buffer
        )
        transcribed_text = transcript.text
        await update.message.reply_text(f"You said: \"{transcribed_text}\"")
        log_event("voice_transcription_success", user_id, {"text": transcribed_text})

        # Now pass the transcribed text to the AI for a response
        # This reuses the ask_ai logic, but without the command prefix
        update.message.text = transcribed_text # Temporarily set text for ask_ai
        await ask_ai(update, context)

    except Exception as e:
        logger.error(f"Error during voice message processing: {e}")
        log_event("voice_transcription_error", user_id, {"error": str(e)})
        await update.message.reply_text("Sorry, I encountered an error while processing your voice message. Please try again later.")

async def image_generation_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_user_premium(user_id):
        await update.message.reply_text("Image generation is a premium feature. Please upgrade to use it.")
        log_event("premium_feature_denied", user_id, {"feature": "image_generation"})
        return

    if not openai_client:
        await update.message.reply_text("OpenAI API key is not configured for image generation. Please contact the administrator.")
        return

    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("Please provide a prompt for image generation. Usage: /generate_image <prompt>")
        return

    await update.message.reply_chat_action("upload_photo")
    await update.message.reply_text(f"Generating image for: \'{prompt}\'...")

    try:
        response = openai_client.images.generate(
            model="dall-e-2", # dall-e-3 is also an option, but dall-e-2 is more widely available
            prompt=prompt,
            n=1,
            size="512x512" # Options: 256x256, 512x512, 1024x1024
        )
        image_url = response.data[0].url
        await update.message.reply_photo(image_url)
        log_event("image_generation_success", user_id, {"prompt": prompt, "image_url": image_url})
    except Exception as e:
        logger.error(f"Error during image generation: {e}")
        log_event("image_generation_error", user_id, {"prompt": prompt, "error": str(e)})
        await update.message.reply_text("Sorry, I encountered an error while generating the image. Please try again later.")

async def file_reading_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_user_premium(user_id):
        await update.message.reply_text("File reading (PDF, TXT) is a premium feature. Please upgrade to use it.")
        log_event("premium_feature_denied", user_id, {"feature": "file_reading"})
        return

    if update.message.document:
        file_name = update.message.document.file_name
        if file_name.endswith(".txt"):
            new_file = await context.bot.get_file(update.message.document.file_id)
            file_buffer = io.BytesIO()
            await new_file.download_to_memory(file_buffer)
            text_content = file_buffer.getvalue().decode("utf-8")
            await update.message.reply_text(f"Content of {file_name}:\n\n{text_content[:1000]}... (truncated)") # Truncate for brevity
            log_event("file_read_success", user_id, {"file_type": "txt", "file_name": file_name})
        elif file_name.endswith(".pdf"):
            new_file = await context.bot.get_file(update.message.document.file_id)
            file_buffer = io.BytesIO()
            await new_file.download_to_memory(file_buffer)
            
            pdf_reader = PdfReader(file_buffer)
            text_content = ""
            for page in pdf_reader.pages:
                text_content += page.extract_text() + "\n"
            
            await update.message.reply_text(f"Content of {file_name}:\n\n{text_content[:1000]}... (truncated)") # Truncate for brevity
            log_event("file_read_success", user_id, {"file_type": "pdf", "file_name": file_name})
        else:
            await update.message.reply_text("I can only read .txt and .pdf files for now.")
            log_event("file_read_unsupported_type", user_id, {"file_name": file_name})
    else:
        await update.message.reply_text("Please send a .txt or .pdf file to read.")

async def youtube_summarizer_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_user_premium(user_id):
        await update.message.reply_text("YouTube/video summarizer is a premium feature. Please upgrade to use it.")
        log_event("premium_feature_denied", user_id, {"feature": "youtube_summarizer"})
        return
    await update.message.reply_text("YouTube/video summarizer is a complex feature and requires additional libraries (e.g., youtube-dl, moviepy) and potentially external APIs for transcription. It is not yet implemented.")
    log_event("youtube_summarizer_not_implemented", user_id)

async def ai_summarization_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if not is_user_premium(user_id):
        await update.message.reply_text("AI summarization tool is a premium feature. Please upgrade to use it.")
        log_event("premium_feature_denied", user_id, {"feature": "ai_summarization"})
        return

    text_to_summarize = " ".join(context.args)
    if not text_to_summarize:
        await update.message.reply_text("Please provide text to summarize. Usage: /summarize <text>")
        return

    await update.message.reply_chat_action("typing")
    await update.message.reply_text("Summarizing your text...")

    try:
        # Reuse AI logic for summarization
        conversation_history = [] # No history for summarization
        system_prompt = "You are a helpful assistant that summarizes text concisely." # Specific prompt for summarization
        current_model_provider = get_user_ai_model(user_id)

        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Summarize the following text: {text_to_summarize}"}]

        if current_model_provider == "groq" and groq_client:
            chat_completion = groq_client.chat.completions.create(
                messages=messages,
                model=GROQ_MODEL_NAME,
                temperature=0.7,
                timeout=API_TIMEOUT
            )
            summary = chat_completion.choices[0].message.content
        elif current_model_provider == "openai" and openai_client:
            chat_completion = openai_client.chat.completions.create(
                messages=messages,
                model=OPENAI_MODEL_NAME,
                temperature=0.7,
                timeout=API_TIMEOUT
            )
            summary = chat_completion.choices[0].message.content
        else:
            await update.message.reply_text("AI model not configured or invalid. Please use /model to select a valid model.")
            return

        await update.message.reply_text(f"Summary: {summary}")
        log_event("ai_summarization_success", user_id, {"text_length": len(text_to_summarize), "summary_length": len(summary)})
    except Exception as e:
        logger.error(f"Error during AI summarization: {e}")
        log_event("ai_summarization_error", user_id, {"error": str(e)})
        await update.message.reply_text("Sorry, I encountered an error while summarizing the text. Please try again later.")

async def main() -> None:
    init_db()
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ask", ask_ai))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, ask_ai)) # Handle direct messages as AI questions
    application.add_handler(CommandHandler("set_prompt", set_prompt))
    application.add_handler(CommandHandler("get_prompt", get_prompt))
    application.add_handler(CommandHandler("forget", forget))
    application.add_handler(CommandHandler("model", change_ai_model_command))
    application.add_handler(CommandHandler("premium", premium_status))
    application.add_handler(CommandHandler("web_search", web_search_command))
    application.add_handler(CommandHandler("generate_image", image_generation_command))
    application.add_handler(CommandHandler("summarize", ai_summarization_command))

    # Admin Commands
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("unban", unban_user))
    application.add_handler(CommandHandler("set_premium", set_premium))

    # Advanced AI Feature Handlers
    application.add_handler(MessageHandler(filters.VOICE, voice_message_handler))
    application.add_handler(MessageHandler(filters.Document.TXT | filters.Document.PDF, file_reading_handler))
    application.add_handler(CommandHandler("youtube_summarize", youtube_summarizer_command))

    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    application.add_handler(CallbackQueryHandler(button_callback_handler))

    logger.info("Bot started polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Sorry, I\\\\'m having trouble connecting to the AI right now. Please try again later.")

if __name__ == "__main__":
    asyncio.run(main())
