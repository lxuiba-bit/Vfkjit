import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8827703579:AAE6ze84LQZbP9TKld_YoryniRFBs40t8mM")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")

# Admin User IDs (replace with actual Telegram User IDs)
ADMIN_IDS = [@agentzu] 

# Default system prompt for AI
DEFAULT_SYSTEM_PROMPT = "You are a ultra helpfull personal  AI assistant."

# SQLite Database Name
DB_NAME = 'bot_memory.db'

# Message rate limit per user (seconds)
RATE_LIMIT_SECONDS = 3

# Timeout for API calls (seconds)
API_TIMEOUT = 30

# Max conversation history length
MAX_HISTORY_LENGTH = 100
