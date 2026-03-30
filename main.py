import os
import requests
import pandas as pd
import asyncio
import logging
from datetime import datetime, timedelta
from telegram import ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

logging.basicConfig(level=logging.INFO)

API_KEY = os.getenv("API_KEY")
TOKEN = os.getenv("BOT_TOKEN")

CHAT_ID = 8167336144

PAIRS = [
    "EURUSD","GBPUSD","USDJPY","AUDUSD","EURJPY",
    "USDCHF","USDCAD","NZDUSD","GBPJPY","EURGBP"
]

bot_active = False
auto_mode = False

last_signal_time = {}
cache = {}

# -----------------------------
def get_cache(key):
    if key in cache:
        data, ts = cache[key]
        if datetime.now() - ts < timedelta(seconds=20):
            return data
    return None

def set_cache(key, data):
    cache[key] = (data, datetime.now())

# -----------------------------
def format_symbol(pair):
    return f"{pair[:3]}/{pair[3:]}"

# -----------------------------
def fetch(symbol, tf):
    key = f"{symbol}_{tf}"

    cached = get_cache(key)
    if cached is not None:
        return cached

    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={tf}&outputsize=100&apikey={API_KEY}"

    try:
        data = requests.get(url).json()
        if "values" not in data:
            return None

        df = pd.DataFrame(data["values"])

        for c in ["open","high","low","close"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df = df.dropna().iloc[::-1].reset_index(drop=True)

        set_cache(key, df)
        return df
    except:
        return None

# -----------------------------
def indicators(df):
    df["ema"] = df["close"].ewm(span=20).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    rs = gain.rolling(14).mean() / (loss.rolling(14).mean() + 1e-10)
    df["rsi"] = 100 - (100/(1+rs))

    ema12 = df["close"].ewm(span=12).mean()
    ema26 = df["close"].ewm(span=26).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9).mean()

    return df

# -----------------------------
def get_expiry(confidence):
    if confidence >= 85:
        return "1 MIN"
    elif confidence >= 80:
        return "2 MIN"
    else:
        return "3 MIN"

# -----------------------------
def analyze(pair):

    now = datetime.now()

    # cooldown
    if pair in last_signal_time:
        if now - last_signal_time[pair] < timedelta(minutes=2):
            return None

    symbol = format_symbol(pair)

    df1 = fetch(symbol, "1min")
    df5 = fetch(symbol, "5min")

    if df1 is None or df5 is None:
        return None

    df1 = indicators(df1)
    df5 = indicators(df5)

    l1 = df1.iloc[-1]
    p1 = df1.iloc[-2]
    l5 = df5.iloc[-1]

    buy = 0
    sell = 0

    # Trend confirmation
    if l1["close"] > l1["ema"] and l5["close"] > l5["ema"]:
        buy += 40
    elif l1["close"] < l1["ema"] and l5["close"] < l5["ema"]:
        sell += 40
    else:
        return None

    # RSI
    if l1["rsi"] < 40:
        buy += 15
    elif l1["rsi"] > 60:
        sell += 15
    else:
        return None

    # MACD
    if l1["macd"] > l1["macd_signal"]:
        buy += 15
    else:
        sell += 15

    # Candle breakout
    if l1["close"] > p1["high"]:
        buy += 20
    elif l1["close"] < p1["low"]:
        sell += 20

    if buy > sell:
        signal = "BUY"
        score = buy
    else:
        signal = "SELL"
        score = sell

    if score < 75:
        return None

    last_signal_time[pair] = now

    return {
        "pair": pair,
        "signal": signal,
        "confidence": int(score)
    }

# -----------------------------
keyboard = [
    ["▶️ Start", "⛔ Stop"],
    ["📊 Signal"]
]

reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# -----------------------------
async def start(update, context):
    global bot_active
    bot_active = True
    await update.message.reply_text("🔥 Sniper V4 Started", reply_markup=reply_markup)

# -----------------------------
async def stop(update, context):
    global bot_active, auto_mode
    bot_active = False
    auto_mode = False
    await update.message.reply_text("⛔ Stopped")

# -----------------------------
async def signal(update, context):
    global auto_mode

    if not bot_active:
        await update.message.reply_text("Start bot first")
        return

    auto_mode = True
    await update.message.reply_text("🚀 Auto Mode ON")

# -----------------------------
async def auto_loop(app):

    global auto_mode

    while True:

        if auto_mode:
            best = None

            for p in PAIRS:
                r = analyze(p)
                if r:
                    if not best or r["confidence"] > best["confidence"]:
                        best = r

            if best:
                expiry = get_expiry(best["confidence"])

                msg = f"""
🚀 SNIPER V4 🚀

PAIR: {best['pair']}
SIGNAL: {best['signal']}
CONFIDENCE: {best['confidence']}%

ENTRY: NEXT CANDLE
EXPIRY: {expiry}
"""

                try:
                    await app.bot.send_message(chat_id=CHAT_ID, text=msg)
                except:
                    pass

        await asyncio.sleep(30)

# -----------------------------
async def button_handler(update, context):
    text = update.message.text

    if text == "▶️ Start":
        await start(update, context)

    elif text == "⛔ Stop":
        await stop(update, context)

    elif text == "📊 Signal":
        await signal(update, context)

# -----------------------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))

    loop = asyncio.get_event_loop()
    loop.create_task(auto_loop(app))

    print("🤖 Sniper V4 Dynamic Expiry Running...")
    app.run_polling()

# -----------------------------
if __name__ == "__main__":
    main()
