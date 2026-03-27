import os
import logging
import random
import datetime
import requests
import pandas as pd
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

API_KEY = "5d41640e898444bb98f7e95f816a8416"
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN not found")

logging.basicConfig(level=logging.INFO)

PAIRS = [
    "EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD",
    "USDCAD","NZDUSD","EURJPY","GBPJPY","AUDJPY"
]

last_signal_time = {}
win_stats = {"win": 0, "loss": 0}

# -----------------------------
# DATA
# -----------------------------
def get_real_data(pair):
    symbol = pair[:3] + "/" + pair[3:]
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=1min&outputsize=50&apikey={API_KEY}"
    r = requests.get(url).json()
    return r.get("values", None)

# -----------------------------
# ANALYSIS
# -----------------------------
def analyze_pair(pair):
    data = get_real_data(pair)
    if data is None:
        return None

    df = pd.DataFrame(data).astype(float).iloc[::-1]

    if len(df) < 20:
        return None

    # Indicators
    df["ema"] = df["close"].ewm(span=10).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + rs))

    # Support/Resistance
    support = df["low"].min()
    resistance = df["high"].max()

    last = df.iloc[-1]
    prev = df.iloc[-2]

    signals = []
    confidence = 0

    # TREND
    if last["close"] > last["ema"]:
        confidence += 30
        trend = "UP"
    else:
        confidence += 15
        trend = "DOWN"

    # RSI
    if last["rsi"] < 30:
        signals.append("BUY")
        confidence += 15
    elif last["rsi"] > 70:
        signals.append("SELL")
        confidence += 15

    # ENGULFING
    if last["close"] > last["open"] and prev["close"] < prev["open"]:
        signals.append("BUY")
        confidence += 10
    if last["close"] < last["open"] and prev["close"] > prev["open"]:
        signals.append("SELL")
        confidence += 10

    # MOMENTUM
    if last["close"] > prev["close"]:
        signals.append("BUY")
        confidence += 5
    else:
        signals.append("SELL")
        confidence += 5

    # -----------------------------
    # FAKE BREAKOUT
    # -----------------------------
    if last["high"] > resistance and last["close"] < resistance:
        signals.append("SELL")
        confidence += 20

    if last["low"] < support and last["close"] > support:
        signals.append("BUY")
        confidence += 20

    # -----------------------------
    # RSI DIVERGENCE (basic)
    # -----------------------------
    if prev["close"] > last["close"] and prev["rsi"] < last["rsi"]:
        signals.append("BUY")
        confidence += 15

    if prev["close"] < last["close"] and prev["rsi"] > last["rsi"]:
        signals.append("SELL")
        confidence += 15

    # FINAL SIGNAL
    if len(signals) == 0:
        return None

    signal = "BUY" if signals.count("BUY") > signals.count("SELL") else "SELL"

    # FINAL FILTER
    if confidence < 75:
        return None

    # COOLDOWN
    now = datetime.datetime.utcnow()
    if pair in last_signal_time:
        if (now - last_signal_time[pair]).seconds < 120:
            return None
    last_signal_time[pair] = now

    return {
        "pair": pair,
        "signal": signal,
        "confidence": min(confidence, 100)
    }

# -----------------------------
# TELEGRAM
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔥 ELITE AI SNIPER ACTIVE 🚀")

async def signals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    results = []

    for pair in PAIRS:
        r = analyze_pair(pair)
        if r:
            results.append(r)

    if not results:
        await update.message.reply_text("❌ No signals")
        return

    results = sorted(results, key=lambda x: x["confidence"], reverse=True)

    msg = "🔥 BEST PAIRS 🔥\n\n"

    for r in results[:3]:
        msg += f"""
PAIR: {r['pair']}
SIGNAL: {r['signal']}
CONFIDENCE: {r['confidence']}%
------------------
"""

    await update.message.reply_text(msg)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = f"📊 Wins: {win_stats['win']} | Loss: {win_stats['loss']}"
    await update.message.reply_text(msg)

# -----------------------------
# MAIN
# -----------------------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("signals", signals))
    app.add_handler(CommandHandler("stats", stats))

    print("🔥 ELITE BOT RUNNING...")
    app.run_polling()

if __name__ == "__main__":
    main()
