import os
import requests
import pandas as pd
import time
from telegram import ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

# -----------------------------
# ENV
# -----------------------------
API_KEY = os.getenv("API_KEY")
TOKEN = os.getenv("BOT_TOKEN")

if not API_KEY or not TOKEN:
    print("❌ API_KEY or BOT_TOKEN missing")
    exit()

CHAT_ID = 8167336144

# ✅ LIMITED BEST PAIRS
PAIRS = ["EURUSD","GBPUSD","USDJPY","AUDUSD","EURJPY"]

bot_active = True

# -----------------------------
def format_symbol(pair):
    return f"{pair[:3]}/{pair[3:]}"

# -----------------------------
def fetch(symbol, interval="1min"):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize=100&apikey={API_KEY}"

    try:
        r = requests.get(url, timeout=10).json()

        if "values" not in r:
            print("❌ API ERROR:", r)
            return None

        df = pd.DataFrame(r["values"])

        for c in ["open","high","low","close"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")

        df = df.dropna().iloc[::-1].reset_index(drop=True)

        return df

    except Exception as e:
        print("❌ Fetch Error:", e)
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
    df["bb_upper"] = df["bb_mid"] + 2*df["bb_std"]
    df["bb_lower"] = df["bb_mid"] - 2*df["bb_std"]

    return df

# -----------------------------
def volatility(df):
    return df["close"].pct_change().abs().mean()

# -----------------------------
def candle(last, prev):
    buy = sell = 0

    if last["close"] > last["open"] and prev["close"] < prev["open"]:
        buy += 10
    if last["close"] < last["open"] and prev["close"] > prev["open"]:
        sell += 10

    return buy, sell

# -----------------------------
def analyze(pair):

    symbol = format_symbol(pair)

    df1 = fetch(symbol, "1min")
    time.sleep(8)   # ✅ FIX: safe API delay

    if df1 is None or len(df1) < 50:
        return None

    if volatility(df1) < 0.00005:   # ✅ FIX: better filter
        return None

    df1 = indicators(df1)

    last = df1.iloc[-1]
    prev = df1.iloc[-2]

    buy = sell = 0

    if last["close"] > last["ema"]:
        buy += 25
    else:
        sell += 25

    if last["rsi"] < 35:
        buy += 15
    elif last["rsi"] > 65:
        sell += 15

    if last["macd"] > last["macd_signal"]:
        buy += 15
    else:
        sell += 15

    if last["close"] < last["bb_lower"]:
        buy += 10
    if last["close"] > last["bb_upper"]:
        sell += 10

    b, s = candle(last, prev)
    buy += b
    sell += s

    # -----------------------------
    # 5 MIN CONFIRM
    # -----------------------------
    df5 = fetch(symbol, "5min")
    time.sleep(5)   # ✅ FIX: safe delay

    if df5 is not None and len(df5) > 20:
        df5 = indicators(df5)
        t = df5.iloc[-1]

        if t["close"] > t["ema"]:
            buy += 20
        else:
            sell += 20

    # -----------------------------
    if buy > sell:
        signal = "BUY"
        score = buy
    else:
        signal = "SELL"
        score = sell

    if score < 50:
        return None

    print(f"✅ {pair} {signal} {score}")

    return {
        "pair": pair,
        "signal": signal,
        "confidence": min(score,100)
    }

# -----------------------------
# BUTTON UI
# -----------------------------
keyboard = [
    ["▶️ Start", "⛔ Stop"],
    ["📊 Signal"]
]

reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# -----------------------------
# HANDLERS
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

    print("🤖 Bot Running with Buttons...")
    app.run_polling(drop_pending_updates=True)

# -----------------------------
if __name__ == "__main__":
    main()
