import os
import time
import requests
import pandas as pd
import logging
import asyncio
from datetime import datetime
from telegram import ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

logging.basicConfig(level=logging.INFO)

API_KEY = os.getenv("API_KEY")
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = 8167336144

PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "EUR/JPY", "USD/CAD", "NZD/USD"]

auto_mode = False
last_signal_time = {p: datetime.min for p in PAIRS}

# -----------------------------
# FETCH DATA FROM API
# -----------------------------
def fetch_data(symbol):
    try:
        # Last 30 candles of 1-minute interval
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=1min&outputsize=30&apikey={API_KEY}"
        response = requests.get(url).json()
        
        if "values" in response:
            df = pd.DataFrame(response["values"])
            df["close"] = df["close"].astype(float)
            df["open"] = df["open"].astype(float)
            # API data reverse hota hai (latest first), isliye flip kar rahe hain
            df = df.iloc[::-1].reset_index(drop=True)
            return df
        else:
            logging.error(f"Error fetching {symbol}: {response}")
            return None
    except Exception as e:
        logging.error(f"API Error: {e}")
        return None

# -----------------------------
# INDICATORS & ANALYSIS
# -----------------------------
def get_indicators(df):
    df["ema_20"] = df["close"].ewm(span=20).mean()
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df["rsi"] = 100 - (100 / (1 + (gain / (loss + 1e-10))))
    return df

def analyze_market(symbol):
    global last_signal_time
    now = datetime.utcnow()

    # Gap logic: 3 minute wait
    if (now - last_signal_time[symbol]).total_seconds() < 180:
        return None

    df = fetch_data(symbol)
    if df is None or len(df) < 20:
        return None

    df = get_indicators(df)
    
    # API data mein last row (index -1) hamesha latest closed candle hoti hai
    curr = df.iloc[-1]
    prev = df.iloc[-2]

    signal = None

    # Logic (Strict for accuracy)
    if curr["close"] > curr["ema_20"] and 50 < curr["rsi"] < 70:
        if curr["close"] > prev["close"]:
            signal = "BUY"
    elif curr["close"] < curr["ema_20"] and 30 < curr["rsi"] < 50:
        if curr["close"] < prev["close"]:
            signal = "SELL"

    if signal:
        last_signal_time[symbol] = now
        return {"pair": symbol, "signal": signal, "entry": round(curr["close"], 5)}
    
    return None

# -----------------------------
# SCANNER ENGINE (Loop)
# -----------------------------
async def scanner_loop(app):
    while True:
        if auto_mode:
            logging.info("Scanning all pairs via API...")
            for pair in PAIRS:
                res = analyze_market(pair)
                if res:
                    await app.bot.send_message(
                        chat_id=CHAT_ID,
                        text=f"""💎 SIGNAL

PAIR: {res['pair']}
ACTION: {res['signal']}
ENTRY: {res['entry']}
EXPIRY: 2 MIN"""
                    )
                # API Rate limit se bachne ke liye chhota delay
                await asyncio.sleep(2) 
        
        # Har 1 minute baad dobara scan karega
        await asyncio.sleep(60)

# -----------------------------
# TELEGRAM SETUP
# -----------------------------
async def post_init(app):
    asyncio.create_task(scanner_loop(app))

async def start(update, context):
    await update.message.reply_text("🚀 Bot Ready (API Mode)", 
        reply_markup=ReplyKeyboardMarkup([["▶️ Start", "⛔ Stop"], ["📊 Signal"]], resize_keyboard=True))

async def buttons(update, context):
    global auto_mode
    text = update.message.text
    if text == "▶️ Start":
        auto_mode = True
        await update.message.reply_text("✅ Bot Started")
    elif text == "⛔ Stop":
        auto_mode = False
        await update.message.reply_text("❌ Auto OFF")
    elif text == "📊 Signal":
        await update.message.reply_text("🔍 Checking latest signals...")
        found = False
        for pair in PAIRS:
            res = analyze_market(pair)
            if res:
                await update.message.reply_text(f"🎯 {res['pair']}: {res['signal']} @ {res['entry']}")
                found = True
        if not found:
            await update.message.reply_text("No clear signals right now.")

def main():
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buttons))
    app.run_polling()

if __name__ == "__main__":
    main()
