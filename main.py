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
CHAT_ID = 8167336144 # Apna Chat ID yahan double check karein

PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "EUR/JPY"]

bot_active = False
auto_mode = False
price_data = {p: [] for p in PAIRS}
last_signal_min = {p: -1 for p in PAIRS}

TRACK_FILE = "track_pro.json"

# -----------------------------
# DATABASE & TRACKING
# -----------------------------
def load_track():
    if not os.path.exists(TRACK_FILE):
        return {"total": 0, "win": 0, "loss": 0}
    try:
        with open(TRACK_FILE, "r") as f: return json.load(f)
    except: return {"total": 0, "win": 0, "loss": 0}

def save_track(data):
    with open(TRACK_FILE, "w") as f: json.dump(data, f)

track_data = load_track()

# -----------------------------
# ADVANCED INDICATORS (ULTRA)
# -----------------------------
def get_indicators(df):
    # 1. Trend Filter (EMA 20 for momentum, EMA 50 for major trend)
    df["ema_20"] = df["close"].ewm(span=20).mean()
    df["ema_50"] = df["close"].ewm(span=50).mean()

    # 2. RSI (Smoothed)
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + (gain / (loss + 1e-10))))

    # 3. Bollinger Bands (Volatility Filter)
    df["std"] = df["close"].rolling(20).std()
    df["upper_bb"] = df["ema_20"] + (df["std"] * 2)
    df["lower_bb"] = df["ema_20"] - (df["std"] * 2)

    # 4. Volume SMA (Smart Money Filter)
    df["vol_sma"] = df["volume"].rolling(10).mean()
    
    # 5. Support & Resistance (Last 20 Candles)
    df["support"] = df["low"].rolling(20).min()
    df["resistance"] = df["high"].rolling(20).max()

    return df

# -----------------------------
# THE "STRONG" ANALYSIS LOGIC
# -----------------------------
def analyze_market(pair):
    now_min = datetime.utcnow().minute
    if last_signal_min[pair] == now_min: return None

    data = price_data[pair]
    if len(data) < 55: return None

    df = pd.DataFrame(data)
    df = get_indicators(df)
    
    curr = df.iloc[-1]  # Current
    prev = df.iloc[-2]  # Previous candle
    
    signal = None
    score = 0

    # Volume Confirmation: Current volume should be > Average volume
    high_vol = curr["volume"] > curr["vol_sma"]

    # --- 💎 ULTRA BUY SIGNAL (High Prob) ---
    # 1. Trend: Above EMA 50
    # 2. Momentum: RSI between 35-50 (Coming from oversold)
    # 3. Breakout: Close > Previous High
    # 4. Safe Zone: Not hitting Upper Bollinger Band or Resistance
    if curr["close"] > curr["ema_50"] and curr["close"] > prev["high"]:
        if 35 < curr["rsi"] < 50 and high_vol:
            if curr["close"] < curr["resistance"]:
                signal = "BUY"
                score = 92

    # --- 💎 ULTRA SELL SIGNAL (High Prob) ---
    # 1. Trend: Below EMA 50
    # 2. Momentum: RSI between 50-65 (Coming from overbought)
    # 3. Breakout: Close < Previous Low
    # 4. Safe Zone: Not hitting Lower Bollinger Band or Support
    elif curr["close"] < curr["ema_50"] and curr["close"] < prev["low"]:
        if 50 < curr["rsi"] < 65 and high_vol:
            if curr["close"] > curr["support"]:
                signal = "SELL"
                score = 92

    if signal and score >= 90:
        last_signal_min[pair] = now_min
        return {"pair": pair, "signal": signal, "confidence": score, "entry": curr["close"]}
    
    return None

# -----------------------------
# AUTO-CHECKER (WIN/LOSS)
# -----------------------------
async def auto_checker(app, pair, entry_price, signal_type):
    await asyncio.sleep(65) # 1-min trade completion
    if pair in price_data and len(price_data[pair]) > 0:
        exit_price = price_data[pair][-1]["close"]
        win = (signal_type == "BUY" and exit_price > entry_price) or \
              (signal_type == "SELL" and exit_price < entry_price)
        
        status = "✅ WIN" if win else "❌ LOSS"
        
        # Stats update
        global track_data
        track_data["total"] += 1
        if win: track_data["win"] += 1
        else: track_data["loss"] += 1
        save_track(track_data)

        msg = f"🏁 PRO RESULT: {pair}\nResult: {status}\nEntry: {entry_price} | Exit: {exit_price}"
        await app.bot.send_message(chat_id=CHAT_ID, text=msg)

# -----------------------------
# ENGINE & TELEGRAM
# -----------------------------
async def websocket_engine(app):
    url = f"wss://ws.twelvedata.com/v1/quotes/price?apikey={API_KEY}"
    while True:
        try:
            async with websockets.connect(url) as ws:
                await ws.send(json.dumps({"action": "subscribe", "params": {"symbols": ",".join(PAIRS)}}))
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    if "symbol" in data and "price" in data:
                        pair, price = data["symbol"], float(data["price"])
                        vol = float(data.get("day_volume", 0)) # Using day_volume for flow check
                        
                        # Candle Logic (1-Min)
                        now = datetime.utcnow().replace(second=0, microsecond=0)
                        if not price_data[pair] or price_data[pair][-1]["time"] != now:
                            price_data[pair].append({"time": now, "open": price, "high": price, "low": price, "close": price, "volume": vol})
                        else:
                            last = price_data[pair][-1]
                            last["high"], last["low"], last["close"] = max(last["high"], price), min(last["low"], price), price
                        
                        if len(price_data[pair]) > 300: price_data[pair].pop(0)

                        if auto_mode:
                            res = analyze_market(pair)
                            if res:
                                msg_txt = f"💎 STRONG SNIPER 💎\n\nPair: {res['pair']}\nSignal: {res['signal']}\nConfidence: {res['confidence']}%\nExpiry: 2 MIN"
                                await app.bot.send_message(chat_id=CHAT_ID, text=msg_txt)
                                asyncio.create_task(auto_checker(app, res['pair'], res['entry'], res['signal']))
        except:
            await asyncio.sleep(5)

async def start(u, c):
    global bot_active
    bot_active = True
    kb = [["▶️ Start", "⛔ Stop"], ["📊 Signal"]]
    await u.message.reply_text("💎 Sniper V5 Ultra-Strong Ready", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

async def handle_buttons(u, c):
    global auto_mode, bot_active
    t = u.message.text
    if t == "▶️ Start": bot_active = True; await u.message.reply_text("System Active.")
    elif t == "⛔ Stop": auto_mode = False; await u.message.reply_text("Auto Scan Off.")
    elif t == "📊 Signal": 
        if bot_active: auto_mode = True; await u.message.reply_text("Scanning for Strong Moves... 🔍")

def main():
    app = ApplicationBuilder().token(TOKEN).post_init(lambda a: asyncio.create_task(websocket_engine(a))).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.run_polling()

if __name__ == "__main__": main()
