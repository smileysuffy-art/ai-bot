import os
import json
import asyncio
import websockets
import pandas as pd
import logging
from datetime import datetime
from telegram import ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

API_KEY = os.getenv("API_KEY")
TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = 8167336144 

# Sirf 7 pairs rakhe hain taaki 8/8 ki limit kabhi hit hi na ho (Safety Margin)
PAIRS = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "EUR/JPY", "USD/CAD", "NZD/USD"]

bot_active = False
auto_mode = False
price_data = {p: [] for p in PAIRS}
last_signal_min = {p: -1 for p in PAIRS}

# -----------------------------
# STRATEGY (FAST & ACCURATE)
# -----------------------------
def get_indicators(df):
    df["ema_20"] = df["close"].ewm(span=20).mean()
    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + (gain / (loss + 1e-10))))
    df["vol_sma"] = df["volume"].rolling(10).mean()
    return df

def analyze_market(pair):
    now_min = datetime.utcnow().minute
    if last_signal_min[pair] == now_min: return None
    data = price_data[pair]
    
    # Wait for only 15 candles now
    if len(data) < 15: return None
    
    df = pd.DataFrame(data)
    df = get_indicators(df)
    curr, prev = df.iloc[-1], df.iloc[-2]
    
    signal = None
    if curr["close"] > curr["ema_20"] and curr["rsi"] > 50 and curr["volume"] > curr["vol_sma"]:
        signal = "BUY"
    elif curr["close"] < curr["ema_20"] and curr["rsi"] < 50 and curr["volume"] > curr["vol_sma"]:
        signal = "SELL"
            
    if signal:
        last_signal_min[pair] = now_min
        return {"pair": pair, "signal": signal, "entry": curr["close"]}
    return None

# -----------------------------
# FIXED ENGINE (FORCE CONNECT)
# -----------------------------
async def websocket_engine(app):
    url = f"wss://ws.twelvedata.com/v1/quotes/price?apikey={API_KEY}"
    while True:
        try:
            async with websockets.connect(url) as ws:
                logging.info("Sending Force Subscriptions...")
                
                # Ek ek karke har pair ko subscribe karo (Slow & Steady)
                for pair in PAIRS:
                    sub_msg = {"action": "subscribe", "params": {"symbols": pair}}
                    await ws.send(json.dumps(sub_msg))
                    await asyncio.sleep(1.5) # Har pair ke beech gap
                    logging.info(f"Sent sub for {pair}")

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
                            last["close"] = price
                            last["volume"] = vol
                        
                        if len(price_data[pair]) > 50: price_data[pair].pop(0)

                        if auto_mode:
                            res = analyze_market(pair)
                            if res:
                                await app.bot.send_message(chat_id=CHAT_ID, text=f"💎 SIGNAL: {res['pair']}\nAction: {res['signal']}\nPrice: {res['entry']}\nExpiry: 2 MIN")
        except Exception as e:
            logging.error(f"WS Error: {e}")
            await asyncio.sleep(5)

# -----------------------------
# MAIN
# -----------------------------
async def post_init(application):
    asyncio.create_task(websocket_engine(application))

async def start(u, c):
    await u.message.reply_text("🚀 Sniper Ready!", reply_markup=ReplyKeyboardMarkup([["▶️ Start", "⛔ Stop"], ["📊 Signal"]], resize_keyboard=True))

async def handle_buttons(u, c):
    global auto_mode
    t = u.message.text
    if t == "▶️ Start": await u.message.reply_text("Bot Active.")
    elif t == "⛔ Stop": auto_mode = False; await u.message.reply_text("Auto OFF.")
    elif t == "📊 Signal": auto_mode = True; await u.message.reply_text("Scanning Market... 🔍")

def main():
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_buttons))
    app.run_polling()

if __name__ == "__main__": main()
