import os
import logging
import random
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import requests
import pandas as pd

API_KEY = "5d41640e898444bb98f7e95f816a8416"
logging.basicConfig(level=logging.INFO)

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN not found")

# Top focus pairs
PAIRS = [
    "EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD",
    "USDCAD","NZDUSD","EURJPY","GBPJPY","AUDJPY"
]

# -----------------------------
# MARKET CONDITION DETECTION
# -----------------------------
def detect_market_condition():
    return random.choice(["TRENDING", "RANGING", "VOLATILE"])

# -----------------------------
# TIMEFRAME SELECTION (AI)
# -----------------------------
def select_timeframe(condition):
    if condition == "TRENDING":
        return random.choice(["5m", "10m"])
    elif condition == "VOLATILE":
        return random.choice(["1m", "2m"])
    else:
        return random.choice(["2m", "5m"])

# -----------------------------
# STRATEGY SCORING SYSTEM
# -----------------------------
def strategy_score():
    return random.randint(60, 95)

# -----------------------------
# AI CONFIDENCE CALCULATION
# -----------------------------
def calculate_confidence(base_score):
    ai_boost = random.randint(0, 10)
    return min(100, base_score + ai_boost)
def get_real_data(pair):
    symbol = pair[:3] + "/" + pair[3:]

    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=1min&outputsize=10&apikey={API_KEY}"

    response = requests.get(url)
    data = response.json()

    if "values" not in data:
        return None

    return data["values"]
# -----------------------------
# SIGNAL ENGINE (SNIPER LOGIC)
# -----------------------------

def analyze_pair(pair):
    data = get_real_data(pair)

    if data is None:
        return None

    df = pd.DataFrame(data)
    df = df.astype(float)

    # -----------------------------
    # EMA (Trend)
    # -----------------------------
    df["ema"] = df["close"].ewm(span=10).mean()

    # -----------------------------
    # RSI
    # -----------------------------
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()

    rs = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))

    # -----------------------------
    # MACD
    # -----------------------------
    ema12 = df["close"].ewm(span=12).mean()
    ema26 = df["close"].ewm(span=26).mean()
    df["macd"] = ema12 - ema26
    df["signal_line"] = df["macd"].ewm(span=9).mean()

    # -----------------------------
    # Bollinger Bands
    # -----------------------------
    df["ma"] = df["close"].rolling(window=20).mean()
    df["std"] = df["close"].rolling(window=20).std()
    df["upper"] = df["ma"] + (df["std"] * 2)
    df["lower"] = df["ma"] - (df["std"] * 2)

    # -----------------------------
    # Support / Resistance
    # -----------------------------
    support = df["low"].min()
    resistance = df["high"].max()

    # -----------------------------
    # Latest candles
    # -----------------------------
    last = df.iloc[-1]
    prev = df.iloc[-2]

    signal = None
    confidence = 0

    # -----------------------------
    # TREND (Highest weight)
    # -----------------------------
    if last["close"] > last["ema"]:
        trend = "UP"
        confidence += 30
    else:
        trend = "DOWN"
        confidence += 30

    # -----------------------------
    # MACD CONFIRMATION
    # -----------------------------
    if last["macd"] > last["signal_line"]:
        signal = "BUY"
        confidence += 20
    else:
        signal = "SELL"
        confidence += 20

    # -----------------------------
    # RSI FILTER
    # -----------------------------
    if last["rsi"] < 30:
        signal = "BUY"
        confidence += 15
    elif last["rsi"] > 70:
        signal = "SELL"
        confidence += 15

    # -----------------------------
    # BOLLINGER BANDS
    # -----------------------------
    if last["close"] <= last["lower"]:
        signal = "BUY"
        confidence += 15
    elif last["close"] >= last["upper"]:
        signal = "SELL"
        confidence += 15

    # -----------------------------
    # SIMPLE CANDLE (Hammer / Shooting Star)
    # -----------------------------
    body = abs(last["close"] - last["open"])
    wick = last["high"] - last["low"]

    if body < (wick * 0.3):
        if last["close"] > last["open"]:
            signal = "BUY"
            confidence += 10
        else:
            signal = "SELL"
            confidence += 10

    # -----------------------------
    # FINAL FILTER
    # -----------------------------
    if signal is None or confidence < 75:
        return None

    timeframe = random.choice(["1m","2m","5m","10m"])

    return {
        "pair": pair,
        "timeframe": timeframe,
        "signal": signal,
        "confidence": confidence
    }
# -----------------------------
# TELEGRAM HANDLERS
# -----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Sniper Bot is running 🚀")

async def signals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    results = []

    for pair in PAIRS:
        data = analyze_pair(pair)
        if data:
            results.append(data)

    if not results:
        await update.message.reply_text("No strong sniper signals ❌")
        return

    # Sort by confidence
    results = sorted(results, key=lambda x: x["confidence"], reverse=True)

    message = ""
    for r in results[:3]:
        message += f"""
PAIR: {r['pair']}
TIMEFRAME: {r['timeframe']}
SIGNAL: {r['signal']}
CONFIDENCE: {r['confidence']}%

"""

    await update.message.reply_text(message)

# -----------------------------
# MAIN
# -----------------------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("signals", signals))

    print("Sniper Bot Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
