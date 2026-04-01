import os
import json
import asyncio
import websockets
import pandas as pd
import logging
import numpy as np
from datetime import datetime, timedelta
from telegram import ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

# Logging Setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Credentials
API_KEY = os.getenv("API_KEY")
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = 8167336144 

# SAFE 8 PAIRS (TwelveData Basic 8 Plan limit)
PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "EUR/JPY", "USD/CAD", "USD/CHF", "NZD/USD"]

bot_active = False
auto_mode = False
price_data = {p: [] for p in PAIRS}
last_signal_min = {p: -1 for p in PAIRS}

TRACK_FILE = "track_pro.json"

# -----------------------------
# DATABASE & TRACKING
# -----------------------------
def load_track():
    if not os.path.exists(TRACK_FILE): return {"total": 0, "win": 0, "loss": 0}
    try:
        with open(TRACK_FILE, "r") as f: return json.load(f)
    except: return {"total": 0, "win": 0, "loss": 0}

def save_track(data):
    with open(TRACK_FILE, "w") as f: json.dump(data, f)

track_data = load_track()

# -----------------------------
# INDICATORS
# -----------------------------
def get_indicators(df):
    df["ema_20"] = df["close"].ewm(span=20).mean()
    df["ema_50"] = df["close"].ewm(span=50).mean()
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + (gain / (loss + 1e-10))))
    df["vol_sma"] = df["volume"].rolling(10).mean()
    df["support"] = df["low"].rolling(20).min()
    df["resistance"] = df["high"].rolling(20).max()
    return df

def analyze_market(pair):
    now_min = datetime.utcnow().minute
    if last_signal_min[pair] == now_min: return None
    data = price_data[pair]
    if len(data) < 55: return None
    df = pd.DataFrame(data)
    df = get_indicators(df)
    curr, prev = df.iloc[-1], df.iloc[-2]
    signal = None
    high_vol = curr["volume"] > curr["vol_sma"]
    if curr["close"] > curr["ema_50"] and curr["close"] > prev["high"]:
        if 35 < curr["rsi"] < 50 and high_vol:
            if curr["close"] < curr["resistance"]: signal = "BUY"
    elif curr["close"] < curr["ema_50"] and curr["close"] < prev["low"]:
        if 50 < curr["rsi"] < 65 and high_vol:
            if curr["close"] > curr["support"]: signal = "SELL"
    if signal:
        last_signal_min[pair] = now_min
        return {"pair": pair, "signal": signal, "entry": curr["close"]}
    return None

# -----------------------------
# ENGINE
# -----------------------------
async def auto_checker(app, pair, entry_price, signal_type):
    await asyncio.sleep(125)
    if pair in price_data and len(price_data[pair]) > 0:
        exit_price = price_data[pair][-1]["close"]
        win = (signal_type == "BUY" and exit_price > entry_price) or (signal_type == "SELL" and exit_price < entry_price)
        status = "✅ WIN" if win else "❌ LOSS"
        global track_data
        track_data["total"] += 1
        if win: track_data["win"] += 1
        else: track_data["loss"] += 1
        save_track(track_data)
        await app.bot.send_message(chat_id=CHAT_ID, text=f"🏁 PRO RESULT: {pair}\nResult: {status}\nEntry: {entry_price} | Exit: {exit_price}")

async def websocket_engine(app):
    url = f"wss://ws.twelvedata.com/v1/quotes/price?apikey={API_KEY}"
    while True:
        try:
            async with websockets.connect(url) as ws:
                logging.info("Starting SAFE 8-Pair Subscription...")
                # Batch of 2 to be 100% safe
                for i in range(0, len(PAIRS), 2):
                    batch = PAIRS[i:i+2]
                    await ws.send(json.dumps({"action": "subscribe", "params": {"symbols": ",".join(batch)}}))
                    await asyncio.sleep(2.5) # Increased delay for safety

                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if "symbol" in data and "price" in data:
                        pair, price = data["symbol"], float(data["price"])
                        vol = float(data.get("day_volume", 0))
                        now = datetime.utcnow().replace(second=0, microsecond=0)
                        if not price_data[pair] or price_data[pair][-1]["time"] != now:
                            price_data[pair].append({"time": now, "open": price, "high": price, "low": price, "close": price, "volume": vol})
                        else:
                            last = price_data[pair][-1]
                            last["high"], last["low"], last["close"] = max(last["high"], price), min(last["low"], price), price
                        if len(price_data[pair]) > 80: price_data[pair].pop(0)
                        if auto_mode:
                            res = analyze_market(pair)
                            if res:
                                await app.bot.send_message(chat_id=CHAT_ID, text=f"💎 STRONG SIGNAL\nPair: {res['pair']}\nAction: {res['signal']}\nExpiry: 2 MIN")
                                asyncio.create_task(auto_checker(app, res['pair'], res['entry'], res['signal']))
        except Exception as e:
            logging.error(f"WS Error: {e}")
            await asyncio.sleep(10)

# -----------------------------
# TELEGRAM & MAIN
# -----------------------------
async def post_init(application):
    asyncio.create_task(websocket_engine(application))

async def start(u, c):
    await u.message.reply_text("💎 Sniper V5 Ultra-Safe Ready", reply_markup=ReplyKeyboardMarkup([["▶️ Start", "⛔ Stop"], ["📊 Signal"]], resize_keyboard=True))

async def handle_buttons(u, c):
    global auto_mode
    t = u.message.text
    if t == "▶️ Start": await u.message.reply_text("System Online.")
    elif t == "⛔ Stop": auto_mode = False; await u.message.reply_text("Auto Mode OFF.")
    elif t == "📊 Signal": auto_mode = True; await u.message.reply_text(f"Scanning {len(PAIRS)} Pairs... 🔍")

def main():
    if not TOKEN: return
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__": main()
