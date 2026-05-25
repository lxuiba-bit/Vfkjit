# ULTRA PRO Telegram AI Agent

This is a powerful Telegram AI bot with multi-model support (Groq/OpenAI), memory, admin features, analytics, and advanced AI capabilities like web search, image generation, voice message processing, and text summarization.

## Features Implemented:

**1. AI Core Features:**
- ChatGPT-style AI replies
- Multi-model support (Groq / OpenAI)
- Smart system prompt control
- Role-based AI personality (via `/set_prompt`)

**2. Memory System:**
- User memory storage (SQLite)
- Long-term conversation history
- Context-aware replies
- Editable memory (`/forget`)

**3. Performance Features:**
- Fast response mode (Groq)
- Timeout protection

**4. Safety & Control System:**
- Anti-spam cooldown system (rate limiting)
- Blocklist / whitelist users (via admin commands)
- Admin-only commands

**5. Admin Panel Features:**
- `/stats` → total users, premium users, message counts, event counts
- `/broadcast` → send message to all users
- `/ban user_id`
- `/unban user_id`
- `/set_premium user_id <0|1>`

**6. Analytics System:**
- Tracks user interactions and events

**7. User Experience Features:**
- Typing animation
- Clean message formatting (Markdown)
- Button menus (Inline keyboards)

**8. Cloud & 24/7 Features:**
- Designed for always-online hosting (Wispbyte compatible)

**9. Advanced AI Features (Premium Level):**
- Voice message AI reply (transcription via OpenAI Whisper, then AI reply)
- Image generation (via OpenAI DALL-E)
- File reading (TXT, PDF)
- Web search integration (via SerpApi)
- AI summarization tool

## Setup and Deployment on Wispbyte.com

### 1. Prerequisites
- A Telegram Bot Token (from BotFather)
- A Groq API Key (from Groq Cloud)
- An OpenAI API Key (for advanced features like voice, image, summarization)
- A SerpApi Key (for web search)
- A Wispbyte.com account

### 2. Configuration
Edit the `config.py` file with your API keys and admin IDs:

```python
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "YOUR_GROQ_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_API_KEY")
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY", "YOUR_SERPAPI_API_KEY")

ADMIN_IDS = [123456789, 987654321] # Replace with your Telegram User IDs
```

**Important:** For production, it is highly recommended to set these as environment variables on your hosting platform instead of hardcoding them in `config.py`.

### 3. Project Structure
Your project directory should look like this:

```
telegram_ai_bot/
├── bot.py
├── config.py
├── requirements.txt
└── Procfile
```

### 4. Procfile for Wispbyte
Create a `Procfile` in the root of your project with the following content:

```
web: python3 bot.py
```

This tells Wispbyte how to start your bot.

### 5. Install Dependencies
The `requirements.txt` file lists all necessary Python packages:

```
python-telegram-bot==20.8
groq==0.4.0
openai==1.30.1
google-search-results
PyPDF2
```
Wispbyte will automatically install these dependencies when you deploy.

### 6. Deployment Steps on Wispbyte.com
1. **Compress your project:** Create a ZIP archive of your `telegram_ai_bot` directory (containing `bot.py`, `config.py`, `requirements.txt`, and `Procfile`).
2. **Log in to Wispbyte:** Go to [https://wispbyte.com/client/dashboard](https://wispbyte.com/client/dashboard) and log in.
3. **Create a new project:** Follow Wispbyte's instructions to create a new project. Choose a Python environment if prompted.
4. **Upload your ZIP file:** Upload the ZIP archive you created in step 1.
5. **Set Environment Variables:** In your Wispbyte project settings, add the following environment variables:
   - `TELEGRAM_BOT_TOKEN`
   - `GROQ_API_KEY`
   - `OPENAI_API_KEY`
   - `SERPAPI_API_KEY`
   (Replace `YOUR_TELEGRAM_BOT_TOKEN`, `YOUR_GROQ_API_KEY`, etc., with your actual keys).
6. **Deploy:** Start or deploy your project. Wispbyte will install dependencies and run your `bot.py` using the `Procfile`.

## Usage

Once deployed, interact with your bot on Telegram:
- Send `/start` to begin.
- Use `/ask <your question>` to chat with the AI.
- Use `/set_prompt <new prompt>` to change the AI's personality.
- Use `/model <groq|openai>` to switch between AI models.
- Send voice messages for transcription and AI replies.
- Use `/generate_image <prompt>` to create images.
- Send `.txt` or `.pdf` files for content reading.
- Use `/web_search <query>` for web searches.
- Use `/summarize <text>` to summarize text.
- Admin commands (`/stats`, `/broadcast`, `/ban`, `/unban`, `/set_premium`) are available to users listed in `ADMIN_IDS`.

Enjoy your ULTRA PRO Telegram AI Agent! 🤖⚡
