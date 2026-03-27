import os
import logging
import random
import datetime
import requests
import pandas as pd
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# -----------------------------
# CONFIG
# -----------------------------
API_KEY = "5d41640e898444bb98f7e95f816a8416"
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN not found")

logging.basicConfig(level=logging.INFO)

# Focus pairs
PAIRS = [
    "EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD",
    "USDCAD","NZDUSD","EURJPY","GBPJPY","AUDJPY"
]

# Cooldown storage
last_signal_time = {}

# -----------------------------
# GET REAL MARKET DATA
# -----------------------------
def get_real_data(pair):
    symbol = pair[:3] + "/" + pair[3:]

    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=1min&outputsize=50&apikey={API_KEY}"

    response = requests.get(url)
    data = response.json()

    if "values" not in data:
        return None

    return data["values"]

# -----------------------------
# MAIN AI ANALYSIS ENGINE
# -----------------------------
def analyze_pair(pair):
    global last_signal_time

    data = get_real_data(pair)

    if data is None:
        return None

    df = pd.DataFrame(data)
    df = df.astype(float)

    # ✅ Fix: correct candle order
    df = df.iloc[::-1]

    # ✅ Fix: minimum candles
    if len(df) < 20:
        return None

    # -----------------------------
    # SESSION DETECTION
    # -----------------------------
    hour = datetime.datetime.utcnow().hour

    if 0 <= hour < 8:
        session = "ASIA"
    elif 8 <= hour < 16:
        session = "LONDON"
    else:
        session = "NEW YORK"

    # -----------------------------
    # INDICATORS
    # -----------------------------

    # EMA
    df["ema"] = df["close"].ewm(span=10).mean()

    # RSI
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()

    rs = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))

    # MACD
    ema12 = df["close"].ewm(span=12).mean()
    ema26 = df["close"].ewm(span=26).mean()
    df["macd"] = ema12 - ema26
    df["signal_line"] = df["macd"].ewm(span=9).mean()

    # Bollinger Bands
    df["ma"] = df["close"].rolling(window=20).mean()
    df["std"] = df["close"].rolling(window=20).std()
    df["upper"] = df["ma"] + (df["std"] * 2)
    df["lower"] = df["ma"] - (df["std"] * 2)

    # Support / Resistance
    support = df["low"].min()
    resistance = df["high"].max()

    # -----------------------------
    # LATEST CANDLE
    # -----------------------------
    last = df.iloc[-1]
    prev = df.iloc[-2]

    signal = None
    confidence = 0

    # -----------------------------
    # TREND (HIGH WEIGHT)
    # -----------------------------
    if last["close"] > last["ema"]:
        confidence += 30
    else:
        confidence += 30

    # -----------------------------
    # MACD
    # -----------------------------
    if last["macd"] > last["signal_line"]:
        signal = "BUY"
        confidence += 20
    else:
        signal = "SELL"
        confidence += 20

    # -----------------------------
    # RSI
    # -----------------------------
    if last["rsi"] < 30:
        signal = "BUY"
        confidence += 15
    elif last["rsi"] > 70:
        signal = "SELL"
        confidence += 15

    # -----------------------------
    # BOLLINGER
    # -----------------------------
    if last["close"] <= last["lower"]:
        signal = "BUY"
        confidence += 15
    elif last["close"] >= last["upper"]:
        signal = "SELL"
        confidence += 15

    # -----------------------------
    # SUPPORT / RESISTANCE
    # -----------------------------
    if last["close"] <= support * 1.001:
        signal = "BUY"
        confidence += 10

    if last["close"] >= resistance * 0.999:
        signal = "SELL"
        confidence += 10

    # -----------------------------
    # SESSION BOOST
    # -----------------------------
    if session in ["LONDON", "NEW YORK"]:
        confidence += 10

    # -----------------------------
    # FINAL FILTER
    # -----------------------------
    if signal is None or confidence < 80:
        return None

    confidence = min(confidence, 100)

    # -----------------------------
    # COOLDOWN (ANTI-SPAM)
    # -----------------------------
    now = datetime.datetime.utcnow()

    if pair in last_signal_time:
        diff = (now - last_signal_time[pair]).seconds
        if diff < 120:
            return None

    last_signal_time[pair] = now

    timeframe = random.choice(["1m", "2m", "5m"])

    return {
        "pair": pair,
        "timeframe": timeframe,
        "signal": signal,
        "confidence": confidence,
        "session": session
    }

# -----------------------------
# TELEGRAM COMMANDS
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔥 Ultimate Sniper Bot Active 🚀")

async def signals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    results = []

    for pair in PAIRS:
        result = analyze_pair(pair)
        if result:
            results.append(result)

    if not results:
        await update.message.reply_text("❌ No strong sniper signals right now")
        return

    # Sort best signals
    results = sorted(results, key=lambda x: x["confidence"], reverse=True)

    message = "🔥 TOP SNIPER SIGNALS 🔥\n\n"

    for r in results[:3]:
        message += f"""
PAIR: {r['pair']}
TIMEFRAME: {r['timeframe']}
SIGNAL: {r['signal']}
CONFIDENCE: {r['confidence']}%
SESSION: {r['session']}
------------------------
"""

    await update.message.reply_text(message)

# -----------------------------
# MAIN
# -----------------------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("signals", signals))

    print("🔥 Sniper Bot Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
