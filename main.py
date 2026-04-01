import os
import json
import asyncio
import websockets
import pandas as pd
import logging
from datetime import datetime, timedelta, time as dtime
from telegram import ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

logging.basicConfig(level=logging.INFO)

API_KEY = os.getenv("API_KEY")
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = 8167336144

PAIRS = ["EUR/USD","GBP/USD","USD/JPY","AUD/USD","EUR/JPY"]

bot_active = False
auto_mode = False

price_data = {p: [] for p in PAIRS}
last_signal_time = {}

# -----------------------------
# TRACKING STORAGE
# -----------------------------
TRACK_FILE = "track.json"

def load_track():
    if not os.path.exists(TRACK_FILE):
        return {"total":0,"win":0,"loss":0}
    try:
        with open(TRACK_FILE,"r") as f:
            return json.load(f)
    except:
        return {"total":0,"win":0,"loss":0}

def save_track(data):
    with open(TRACK_FILE,"w") as f:
        json.dump(data,f)

track_data = load_track()

# -----------------------------
# UPDATE RESULT (SIMPLIFIED TRACKING)
# -----------------------------
def update_result(signal, result):
    global track_data
    track_data["total"] += 1

    if result == "WIN":
        track_data["win"] += 1
    else:
        track_data["loss"] += 1

    save_track(track_data)

# -----------------------------
# DAILY REPORT
# -----------------------------
async def daily_report(app):
    while True:
        now = datetime.utcnow()

        # send at UTC midnight
        if now.hour == 0 and now.minute == 0:
            total = track_data["total"]
            win = track_data["win"]
            loss = track_data["loss"]

            winrate = (win/total*100) if total > 0 else 0

            msg = f"""
📊 DAILY REPORT 📊

Total Signals: {total}
Wins: {win}
Losses: {loss}
Win Rate: {winrate:.2f}%
"""
            try:
                await app.bot.send_message(chat_id=CHAT_ID, text=msg)
            except:
                pass

            await asyncio.sleep(60)  # prevent duplicate send

        await asyncio.sleep(30)

# -----------------------------
# CANDLE BUILD
# -----------------------------
def build_candle(pair, price):
    now = datetime.utcnow().replace(second=0, microsecond=0)

    if not price_data[pair]:
        price_data[pair].append({
            "time": now,
            "open": price,
            "high": price,
            "low": price,
            "close": price
        })
        return

    last = price_data[pair][-1]

    if last["time"] == now:
        last["high"] = max(last["high"], price)
        last["low"] = min(last["low"], price)
        last["close"] = price
    else:
        price_data[pair].append({
            "time": now,
            "open": price,
            "high": price,
            "low": price,
            "close": price
        })

# -----------------------------
# INDICATORS
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
# EXPIRY
# -----------------------------
def get_expiry(confidence):
    if confidence >= 85:
        return "1 MIN"
    elif confidence >= 80:
        return "2 MIN"
    else:
        return "3 MIN"

# -----------------------------
# ANALYZE
# -----------------------------
def analyze(pair):

    now = datetime.now()

    if pair in last_signal_time:
        if now - last_signal_time[pair] < timedelta(minutes=5):
            return None

    data = price_data[pair]

    if len(data) < 30:
        return None

    df = pd.DataFrame(data)
    df = indicators(df)

    l1 = df.iloc[-1]
    p1 = df.iloc[-2]

    buy = 0
    sell = 0

    if l1["close"] > l1["ema"]:
        buy += 40
    else:
        sell += 40

    if l1["rsi"] < 40:
        buy += 15
    elif l1["rsi"] > 60:
        sell += 15
    else:
        return None

    if l1["macd"] > l1["macd_signal"]:
        buy += 15
    else:
        sell += 15

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
# KEYBOARD
# -----------------------------
keyboard = [
["▶️ Start", "⛔ Stop"],
["📊 Signal"]
]

reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# -----------------------------
# COMMANDS
# -----------------------------
async def start(update, context):
    global bot_active
    bot_active = True
    await update.message.reply_text("🔥 Sniper V5 Started", reply_markup=reply_markup)

async def stop(update, context):
    global bot_active, auto_mode
    bot_active = False
    auto_mode = False
    await update.message.reply_text("⛔ Stopped")

async def signal(update, context):
    global auto_mode

    if not bot_active:
        await update.message.reply_text("Start bot first")
        return

    auto_mode = True
    await update.message.reply_text("🚀 Auto Mode ON")

# -----------------------------
# WEBSOCKET LOOP
# -----------------------------
async def websocket_loop(app):

    url = f"wss://ws.twelvedata.com/v1/quotes/price?apikey={API_KEY}"

    async with websockets.connect(url) as ws:

        await ws.send(json.dumps({
            "action": "subscribe",
            "params": {
                "symbols": ",".join(PAIRS)
            }
        }))

        while True:
            msg = await ws.recv()
            data = json.loads(msg)

            if "symbol" in data and "price" in data:
                pair = data["symbol"]
                price = float(data["price"])

                if pair not in price_data:
                    continue

                build_candle(pair, price)

                if auto_mode:
                    result = analyze(pair)

                    if result:
                        expiry = get_expiry(result["confidence"])

                        message = f"""
🚀 SNIPER V5 🚀

PAIR: {result['pair']}
SIGNAL: {result['signal']}
CONFIDENCE: {result['confidence']}%

ENTRY: NEXT CANDLE
EXPIRY: {expiry}
"""
                        try:
                            await app.bot.send_message(chat_id=CHAT_ID, text=message)

                            # OPTIONAL: simulate result tracking (placeholder)
                            # here you can later connect real win/loss logic
                            update_result(result["signal"], "WIN")

                        except:
                            pass

# -----------------------------
# BUTTON HANDLER
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
# STARTUP
# -----------------------------
async def on_startup(app):
    asyncio.create_task(websocket_loop(app))
    asyncio.create_task(daily_report(app))

# -----------------------------
# MAIN
# -----------------------------
def main():
    app = ApplicationBuilder().token(TOKEN).post_init(on_startup).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, button_handler))

    print("🔥 Sniper V5 WebSocket Running...")

    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
