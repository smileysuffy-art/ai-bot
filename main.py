import os
import requests
import pandas as pd
import asyncio
import datetime
import json
import time
from telegram.ext import ApplicationBuilder, CommandHandler

# -----------------------------
# ENV
# -----------------------------
API_KEY = os.getenv("API_KEY")
TOKEN = os.getenv("BOT_TOKEN")

CHAT_ID = 8167336144

# -----------------------------
# PAIRS
# -----------------------------
PAIRS = [
    "EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","USDCAD","NZDUSD",
    "EURJPY","GBPJPY","AUDJPY","EURGBP","EURAUD","EURCAD","EURCHF",
    "GBPCHF","GBPAUD","GBPCAD","AUDCAD","AUDCHF","AUDNZD","CADJPY",
    "CHFJPY","NZDJPY","EURNZD","GBPNZD"
]

BATCH_SIZE = 5
REQUEST_DELAY = 2

# -----------------------------
# MEMORY WEIGHTS
# -----------------------------
memory = {
    "TREND":2,
    "CANDLE":2,
    "RSI":1,
    "MACD":1,
    "BB":1,
    "BREAKOUT":2
}

def w(k): return memory.get(k,1)

# -----------------------------
# FETCH DATA
# -----------------------------
def get_data(pair):
    symbol = f"{pair[:3]}/{pair[3:]}"
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=1min&outputsize=100&apikey={API_KEY}"

    try:
        res = requests.get(url, timeout=10).json()
        if "values" not in res:
            return None

        df = pd.DataFrame(res["values"])

        for c in ["open","high","low","close"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df = df.dropna().iloc[::-1].reset_index(drop=True)
        return df
    except:
        return None

# -----------------------------
# INDICATORS
# -----------------------------
def compute(df):
    df["ema"] = df["close"].ewm(span=10).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(14).mean() / (loss.rolling(14).mean() + 1e-10)
    df["rsi"] = 100 - (100 / (1 + rs))

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
# CANDLE PATTERNS (SIMPLIFIED)
# -----------------------------
def candle_signal(last, prev):
    buy, sell = 0,0

    # Engulfing
    if last["close"] > last["open"] and prev["close"] < prev["open"]:
        buy += 10
    if last["close"] < last["open"] and prev["close"] > prev["open"]:
        sell += 10

    # Hammer / Shooting star approximation
    body = abs(last["close"] - last["open"])
    range_ = last["high"] - last["low"]

    if range_ > 0 and body/range_ < 0.3:
        if last["close"] > last["open"]:
            buy += 5
        else:
            sell += 5

    return buy, sell

# -----------------------------
# MARKET CONDITION
# -----------------------------
def market_type(df):
    volatility = df["close"].rolling(10).std().iloc[-1]

    if volatility < 0.0005:
        return "RANGE"
    elif df["close"].iloc[-1] > df["ema"].iloc[-1]:
        return "TREND_UP"
    else:
        return "TREND_DOWN"

# -----------------------------
# ANALYSIS ENGINE
# -----------------------------
def analyze(pair):
    df = get_data(pair)
    time.sleep(REQUEST_DELAY)

    if df is None or len(df) < 50:
        return None

    df = compute(df)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    buy, sell = 0,0

    # TREND
    if last["close"] > last["ema"]:
        buy += 30 * w("TREND")
    else:
        sell += 30 * w("TREND")

    # RSI
    if last["rsi"] < 30:
        buy += 15 * w("RSI")
    elif last["rsi"] > 70:
        sell += 15 * w("RSI")

    # MACD
    if last["macd"] > last["macd_signal"]:
        buy += 15 * w("MACD")
    else:
        sell += 15 * w("MACD")

    # BB
    if last["close"] < last["bb_lower"]:
        buy += 10 * w("BB")
    if last["close"] > last["bb_upper"]:
        sell += 10 * w("BB")

    # CANDLE
    b,s = candle_signal(last, prev)
    buy += b * w("CANDLE")
    sell += s * w("CANDLE")

    # BREAKOUT
    resistance = df["high"].rolling(20).max().iloc[-2]
    support = df["low"].rolling(20).min().iloc[-2]

    if last["close"] > resistance:
        buy += 15 * w("BREAKOUT")
    if last["close"] < support:
        sell += 15 * w("BREAKOUT")

    # MARKET FILTER
    mkt = market_type(df)

    if mkt == "RANGE":
        buy *= 0.8
        sell *= 0.8

    # FINAL DECISION
    if buy > sell:
        signal = "BUY"
        confidence = buy
    else:
        signal = "SELL"
        confidence = sell

    if confidence < 70:
        return None

    confidence = min(confidence, 100)

    return {
        "pair": pair,
        "signal": signal,
        "confidence": confidence,
        "market": mkt
    }

# -----------------------------
# BATCH SCANNER
# -----------------------------
async def scan(app):
    i = 0

    while True:
        batch = PAIRS[i:i+BATCH_SIZE]

        for p in batch:
            r = analyze(p)

            if r:
                msg = f"""🚀 AI NEXT LEVEL SIGNAL 🚀

PAIR: {r['pair']}
SIGNAL: {r['signal']}
CONFIDENCE: {r['confidence']}%
MARKET: {r['market']}
"""
                try:
                    await app.bot.send_message(chat_id=CHAT_ID, text=msg)
                except:
                    pass

        i += BATCH_SIZE
        if i >= len(PAIRS):
            i = 0

        await asyncio.sleep(25)

# -----------------------------
# START
# -----------------------------
async def start(update, context):
    await update.message.reply_text("🔥 Next Level Bot Running")

async def post_init(app):
    app.create_task(scan(app))

def main():
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))

    print("🤖 Running...")
    app.run_polling()

if __name__ == "__main__":
    main()
