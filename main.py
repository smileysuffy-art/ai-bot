import os
import requests
import pandas as pd
import asyncio
import datetime
import json
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# -----------------------------
# CONFIG
# -----------------------------
API_KEY = "YOUR_API_KEY"
TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
CHAT_ID = 123456789

PAIRS = [
    "EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","USDCAD","NZDUSD",
    "EURJPY","GBPJPY","AUDJPY","EURGBP","EURAUD","EURCAD","EURCHF",
    "GBPCHF","GBPAUD","GBPCAD",
    "AUDCAD","AUDCHF","AUDNZD","CADJPY","CHFJPY","NZDJPY",
    "EURNZD","GBPNZD"
]

# -----------------------------
# MEMORY (SELF LEARNING READY)
# -----------------------------
MEMORY_FILE = "memory.json"

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {"RSI":1,"MACD":1,"TREND":1,"CANDLE":1,"BB":1}
    with open(MEMORY_FILE,"r") as f:
        return json.load(f)

def save_memory(mem):
    with open(MEMORY_FILE,"w") as f:
        json.dump(mem,f)

memory = load_memory()

def get_weight(key):
    return memory.get(key,1)

# (ready for future learning loop)
def update_weight(key, win):
    if win:
        memory[key] = memory.get(key,1) + 0.05
    else:
        memory[key] = memory.get(key,1) - 0.03

    memory[key] = max(0.5, min(memory[key],3))
    save_memory(memory)

# -----------------------------
# COOLDOWN CONTROL
# -----------------------------
last_signal_time = {}

# -----------------------------
# SYMBOL FORMAT
# -----------------------------
def format_symbol(pair):
    return f"{pair[:3]}/{pair[3:]}"

# -----------------------------
# FETCH DATA
# -----------------------------
def get_data(pair):
    symbol = format_symbol(pair)
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=1min&outputsize=100&apikey={API_KEY}"

    try:
        res = requests.get(url, timeout=10).json()

        if res.get("status") == "error" or "values" not in res:
            return None

        df = pd.DataFrame(res["values"])
        df = df.astype(float).iloc[::-1].reset_index(drop=True)
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
    df["bb_upper"] = df["bb_mid"] + 2*df["bb_std"]
    df["bb_lower"] = df["bb_mid"] - 2*df["bb_std"]

    return df

# -----------------------------
# CANDLE PATTERN
# -----------------------------
def candle_score(last, prev):
    buy = 0
    sell = 0

    if last["close"] > last["open"] and prev["close"] < prev["open"]:
        buy += 10
    if last["close"] < last["open"] and prev["close"] > prev["open"]:
        sell += 10

    body = abs(last["close"] - last["open"])
    wick = last["high"] - last["low"]

    if body < wick * 0.3:
        buy += 5
        sell += 5

    return buy, sell

# -----------------------------
# ANALYSIS ENGINE
# -----------------------------
def analyze(pair):

    df = get_data(pair)
    if df is None or len(df) < 30:
        return None

    df = compute(df)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    buy_score = 0
    sell_score = 0

    # TREND
    if last["close"] > last["ema"]:
        buy_score += 30 * get_weight("TREND")
    else:
        sell_score += 30 * get_weight("TREND")

    # RSI
    if last["rsi"] < 30:
        buy_score += 15 * get_weight("RSI")
    elif last["rsi"] > 70:
        sell_score += 15 * get_weight("RSI")

    # MACD
    if last["macd"] > last["macd_signal"]:
        buy_score += 15 * get_weight("MACD")
    else:
        sell_score += 15 * get_weight("MACD")

    # Bollinger
    if last["close"] < last["bb_lower"]:
        buy_score += 10 * get_weight("BB")
    if last["close"] > last["bb_upper"]:
        sell_score += 10 * get_weight("BB")

    # Candle
    b, s = candle_score(last, prev)
    buy_score += b * get_weight("CANDLE")
    sell_score += s * get_weight("CANDLE")

    # FINAL DECISION
    if buy_score > sell_score:
        signal = "BUY"
        confidence = buy_score
    else:
        signal = "SELL"
        confidence = sell_score

    if confidence < 65:
        return None

    confidence = min(confidence, 100)

    now = datetime.datetime.utcnow()

    # cooldown per pair
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
# AUTO SIGNAL
# -----------------------------
async def auto_signal(context: ContextTypes.DEFAULT_TYPE):

    loop = asyncio.get_running_loop()
    tasks = [loop.run_in_executor(None, analyze, p) for p in PAIRS]

    results = await asyncio.gather(*tasks)

    for r in results:
        if r:
            msg = f"""
🚀 AI SIGNAL 🚀

PAIR: {r['pair']}
SIGNAL: {r['signal']}
CONFIDENCE: {r['confidence']}%
"""
            await context.bot.send_message(chat_id=CHAT_ID, text=msg)

# -----------------------------
async def start(update, context):
    await update.message.reply_text("🔥 UPGRADED AI BOT ACTIVE")

# -----------------------------
def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.job_queue.run_repeating(auto_signal, interval=30, first=5)

    print("🚀 BOT RUNNING...")
    app.run_polling()

if __name__ == "__main__":
    main()
