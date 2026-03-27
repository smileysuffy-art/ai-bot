import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Logging enable (debug ke liye useful)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.getenv("import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Logging enable (debug ke liye useful)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TOKEN = os.getenv("BOT_TOKEN")

# Safety check
if not TOKEN:
    raise ValueError("BOT_TOKEN not found in environment variables")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is working 🚀")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()")

# Safety check
if not TOKEN:
    raise ValueError("BOT_TOKEN not found in environment variables")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is working 🚀")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
