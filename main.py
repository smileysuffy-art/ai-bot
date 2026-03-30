import os
import requests
import pandas as pd
import time
import logging
from datetime import datetime, timedelta
from telegram import ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

# -----------------------------
# LOGGING
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# -----------------------------
# ENV
# -----------------------------
API_KEY = os.getenv("API_KEY")
TOKEN = os.getenv("BOT_TOKEN")

if not API_KEY or not TOKEN:
    logging.error("❌ API_KEY or BOT_TOKEN missing")
    exit()

PAIRS = ["EURUSD","GBPUSD","USDJPY","AUDUSD","EURJPY"]

bot_active = True

# -----------------------------
# CACHE
# -----------------------------
cache = {}

def get_cache(key):
    try:
        if key in cache:
            data, ts = cache[key]
            if datetime.now() - ts < timedelta(seconds=30):
                return data
    except:
        pass
    return None

def set_cache(key, data):
    cache[key] = (data, datetime.now())

# -----------------------------
def format_symbol(pair):
    return f"{pair[:3]}/{pair[3:]}"

# -----------------------------
def fetch(symbol, interval="1min"):
    key = f"{symbol}_{interval}"

    cached = get_cache(key)
    if cached is not None:
        return cached

    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize=100&apikey={API_KEY}"

    try:
        r = requests.get(url, timeout=10)

        if r.status_code != 200:
            logging.warning(f"API HTTP Error: {r.status_code}")
            return None

        data = r.json()

        if "values" not in data:
            logging.warning(f"API Response Error: {data}")
            return None

        df = pd.DataFrame(data["values"])

        for c in ["open","high","low","close"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df = df.dropna().iloc[::-1].reset_index(drop=True)

        set_cache(key, df)
        return df

    except Exception as e:
        logging.error(f"Fetch Error: {e}")
        return None

# -----------------------------
def indicators(df):
    df["ema"] = df["close"].ewm(span=10).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    rs = gain.rolling(14).mean() / (loss.rolling(14).mean() + 1e-10)
    df["rsi"] = 100 - (100/(1+rs))

    ema12 = df["close"].ewm(span=12).mean()
    ema26 = df["close"].ewm(span=26).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9).mean()

    df["bb_mid"] = df["close"].rolling(20).mean()
    df["bb_std"] = df["close"].rolling(20).std()
    df["bb_upper"] = df["bb_mid"] + 2 * df["bb_std"]
    df["bb_lower"] = df["bb_mid"] - 2 * df["bb_std"]

    return df

# -----------------------------
def volatility(df):
    return df["close"].pct_change().abs().mean()

# -----------------------------
def candle(last, prev):
    buy = 0
    sell = 0

    if last["close"] > last["open"] and prev["close"] < prev["open"]:
        buy += 10

    if last["close"] < last["open"] and prev["close"] > prev["open"]:
        sell += 10

    return buy, sell

# -----------------------------
def market_structure(df):
    if len(df) < 3:
        return 0

    if df["high"].iloc[-1] > df["high"].iloc[-2] and df["low"].iloc[-1] > df["low"].iloc[-2]:
        return 1
    elif df["high"].iloc[-1] < df["high"].iloc[-2] and df["low"].iloc[-1] < df["low"].iloc[-2]:
        return -1
    return 0

# -----------------------------
def analyze(pair):

    symbol = format_symbol(pair)

    df1 = fetch(symbol, "1min")
    time.sleep(0.2)

    if df1 is None or len(df1) < 50:
        return None

    vol = volatility(df1)

    if vol < 0.00002 or vol > 0.02:
        return None

    df1 = indicators(df1)

    last = df1.iloc[-1]
    prev = df1.iloc[-2]

    buy = 0
    sell = 0

    # TREND
    if last["close"] > last["ema"]:
        buy += 30
    else:
        sell += 30

    # STRUCTURE
    structure = market_structure(df1)
    if structure == 1:
        buy += 25
    elif structure == -1:
        sell += 25

    # RSI
    if last["rsi"] < 40:
        buy += 10
    elif last["rsi"] > 60:
        sell += 10

    # MACD
    if last["macd"] > last["macd_signal"]:
        buy += 10
    else:
        sell += 10

    # BOLLINGER
    if last["close"] < last["bb_lower"]:
        buy += 10
    elif last["close"] > last["bb_upper"]:
        sell += 10

    # CANDLE
    b, s = candle(last, prev)
    buy += b
    sell += s

    # 5 MIN CONFIRMATION
    df5 = fetch(symbol, "5min")
    time.sleep(0.2)

    if df5 is not None and len(df5) > 20:
        df5 = indicators(df5)
        t = df5.iloc[-1]

        if t["close"] > t["ema"]:
            buy += 15
        else:
            sell += 15

    # FINAL DECISION
    if buy > sell:
        signal = "BUY"
        score = buy
    else:
        signal = "SELL"
        score = sell

    if score < 70:
        return None

    confidence = min(score, 100)

    entry = "NOW / NEXT CANDLE" if confidence >= 80 else "NEXT CANDLE"

    # ✅ UPGRADED EXPIRY LOGIC
    if confidence >= 85 and vol > 0.0008:
        expiry = "1 MIN"
    elif confidence >= 75:
        expiry = "2 MIN"
    elif confidence >= 65:
        expiry = "3 MIN"
    else:
        expiry = "5 MIN"

    return {
        "pair": pair,
        "signal": signal,
        "confidence": confidence,
        "entry": entry,
        "expiry": expiry
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
    await update.message.reply_text("🔥 Bot Started", reply_markup=reply_markup)

# -----------------------------
async def stop(update, context):
    global bot_active
    bot_active = False
    await update.message.reply_text("⛔ Bot Stopped", reply_markup=reply_markup)

# -----------------------------
async def signal(update, context):

    if not bot_active:
        await update.message.reply_text("⚠️ Bot stopped. Press Start")
        return

    await update.message.reply_text("⏳ Scanning market...")

    found = False

    for p in PAIRS:
        r = analyze(p)

        if r:
            found = True

            msg = f"""🚀 SIGNAL 🚀

PAIR: {r['pair']}
SIGNAL: {r['signal']}
CONFIDENCE: {r['confidence']}%

ENTRY: {r['entry']}
EXPIRY: {r['expiry']}
"""

            await update.message.reply_text(msg)

    if not found:
        await update.message.reply_text("❌ No strong signal")

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

    logging.info("🤖 Bot Running...")
    app.run_polling(drop_pending_updates=True)

# -----------------------------
if __name__ == "__main__":
    main()
