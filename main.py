import os
import logging
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

PAIRS = [
    "EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD",
    "USDCAD","NZDUSD","EURJPY","GBPJPY","AUDJPY"
]

last_signal_time = {}

# -----------------------------
# DATA FETCH
# -----------------------------
def get_real_data(pair):
    symbol = pair[:3] + "/" + pair[3:]
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=1min&outputsize=60&apikey={API_KEY}"

    try:
        r = requests.get(url, timeout=10).json()
        if "values" not in r:
            return None
        return r["values"]
    except:
        return None

# -----------------------------
# INDICATORS
# -----------------------------
def compute_indicators(df):
    df = df.astype(float).iloc[::-1]

    # EMA
    df["ema"] = df["close"].ewm(span=10).mean()

    # RSI
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / (avg_loss + 1e-10)
    df["rsi"] = 100 - (100 / (1 + rs))

    return df

# -----------------------------
# ANALYSIS ENGINE
# -----------------------------
def analyze_pair(pair):
    data = get_real_data(pair)
    if data is None:
        return None

    df = pd.DataFrame(data)

    if len(df) < 25:
        return None

    df = compute_indicators(df)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # Support & Resistance (exclude last candle)
    support = df["low"].iloc[:-1].min()
    resistance = df["high"].iloc[:-1].max()

    signals = []
    confidence = 0

    # -----------------------------
    # TREND
    # -----------------------------
    if last["close"] > last["ema"]:
        signals.append("BUY")
        confidence += 25
        trend = "UP"
    else:
        signals.append("SELL")
        confidence += 20
        trend = "DOWN"

    # -----------------------------
    # RSI
    # -----------------------------
    if last["rsi"] < 30:
        signals.append("BUY")
        confidence += 20
    elif last["rsi"] > 70:
        signals.append("SELL")
        confidence += 20

    # -----------------------------
    # ENGULFING
    # -----------------------------
    if last["close"] > last["open"] and prev["close"] < prev["open"]:
        signals.append("BUY")
        confidence += 10

    if last["close"] < last["open"] and prev["close"] > prev["open"]:
        signals.append("SELL")
        confidence += 10

    # -----------------------------
    # MOMENTUM
    # -----------------------------
    if last["close"] > prev["close"]:
        signals.append("BUY")
        confidence += 5
    else:
        signals.append("SELL")
        confidence += 5

    # -----------------------------
    # SUPPORT / RESISTANCE
    # -----------------------------
    if last["close"] <= support:
        signals.append("BUY")
        confidence += 10

    if last["close"] >= resistance:
        signals.append("SELL")
        confidence += 10

    # -----------------------------
    # DECISION LOGIC
    # -----------------------------
    buy_count = signals.count("BUY")
    sell_count = signals.count("SELL")

    if buy_count >= 3 and buy_count > sell_count:
        signal = "BUY"
    elif sell_count >= 3 and sell_count > buy_count:
        signal = "SELL"
    else:
        return None

    # Confidence filter
    if confidence < 75:
        return None

    confidence = min(confidence, 100)

    # -----------------------------
    # COOLDOWN
    # -----------------------------
    now = datetime.datetime.utcnow()

    if pair in last_signal_time:
        if (now - last_signal_time[pair]).seconds < 120:
            return None

    last_signal_time[pair] = now

    return {
        "pair": pair,
        "signal": signal,
        "confidence": confidence
    }

# -----------------------------
# TELEGRAM HANDLERS
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 Optimized Elite Sniper Bot Active")

async def signals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    results = []

    for pair in PAIRS:
        r = analyze_pair(pair)
        if r:
            results.append(r)

    if not results:
        await update.message.reply_text("❌ No strong signals")
        return

    results = sorted(results, key=lambda x: x["confidence"], reverse=True)

    msg = "🔥 TOP SIGNALS 🔥\n\n"

    for r in results[:3]:
        msg += f"""
PAIR: {r['pair']}
SIGNAL: {r['signal']}
CONFIDENCE: {r['confidence']}%
------------------
"""

    await update.message.reply_text(msg)

# -----------------------------
# MAIN
# -----------------------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("signals", signals))

    print("🚀 Optimized Bot Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
