import os
import json
import asyncio
import websockets
import pandas as pd
import logging
from datetime import datetime
from telegram import ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

logging.basicConfig(level=logging.INFO)

API_KEY = os.getenv("API_KEY")
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = 8167336144

PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "EUR/JPY", "USD/CAD", "NZD/USD"]

auto_mode = False
price_data = {p: [] for p in PAIRS}
last_signal_min = {p: -1 for p in PAIRS}

# -----------------------------
# INDICATORS
# -----------------------------
def get_indicators(df):
    df["ema_20"] = df["close"].ewm(span=20).mean()

    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + (gain / (loss + 1e-10))))

    return df

# -----------------------------
# ANALYSIS
# -----------------------------
def analyze_market(pair):
    now_min = datetime.utcnow().minute

    if last_signal_min[pair] == now_min:
        return None

    data = price_data[pair]

    if len(data) < 15:
        return None

    df = pd.DataFrame(data)
    df = get_indicators(df)

    curr = df.iloc[-1]
    prev = df.iloc[-2]

    signal = None

    # 🔥 RELAXED + BETTER CONDITIONS
    if curr["close"] > curr["ema_20"] and curr["rsi"] > 48:
        signal = "BUY"

    elif curr["close"] < curr["ema_20"] and curr["rsi"] < 52:
        signal = "SELL"

    # 🔥 CANDLE CONFIRMATION
    if signal == "BUY" and curr["close"] < prev["close"]:
        signal = None

    if signal == "SELL" and curr["close"] > prev["close"]:
        signal = None

    if signal:
        last_signal_min[pair] = now_min
        return {
            "pair": pair,
            "signal": signal,
            "entry": curr["close"]
        }

    return None

# -----------------------------
# WEBSOCKET ENGINE
# -----------------------------
async def websocket_engine(app):
    url = f"wss://ws.twelvedata.com/v1/quotes/price?apikey={API_KEY}"

    while True:
        try:
            async with websockets.connect(url) as ws:
                logging.info("Connected to WebSocket")

                for pair in PAIRS:
                    await ws.send(json.dumps({
                        "action": "subscribe",
                        "params": {"symbols": pair}
                    }))
                    await asyncio.sleep(1)

                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)

                    if "symbol" in data and "price" in data:
                        pair = data["symbol"]
                        price = float(data["price"])

                        now = datetime.utcnow().replace(second=0, microsecond=0)

                        if not price_data[pair] or price_data[pair][-1]["time"] != now:
                            price_data[pair].append({
                                "time": now,
                                "open": price,
                                "high": price,
                                "low": price,
                                "close": price
                            })
                        else:
                            last = price_data[pair][-1]
                            last["close"] = price
                            last["high"] = max(last["high"], price)
                            last["low"] = min(last["low"], price)

                        if len(price_data[pair]) > 50:
                            price_data[pair].pop(0)

                        if auto_mode:
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

        except Exception as e:
            logging.error(f"WS Error: {e}")
            await asyncio.sleep(5)

# -----------------------------
# TELEGRAM
# -----------------------------
async def post_init(app):
    asyncio.create_task(websocket_engine(app))

async def start(update, context):
    await update.message.reply_text(
        "🚀 Bot Ready",
        reply_markup=ReplyKeyboardMarkup(
            [["▶️ Start", "⛔ Stop"], ["📊 Signal"]],
            resize_keyboard=True
        )
    )

async def buttons(update, context):
    global auto_mode
    text = update.message.text

    if text == "▶️ Start":
        await update.message.reply_text("✅ Bot Started")

    elif text == "⛔ Stop":
        auto_mode = False
        await update.message.reply_text("❌ Auto OFF")

    elif text == "📊 Signal":
        auto_mode = True
        await update.message.reply_text("🔍 Scanning...")

# -----------------------------
def main():
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buttons))

    app.run_polling()

if __name__ == "__main__":
    main()
