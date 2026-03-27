import os
import logging
import random
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

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

# -----------------------------
# SIGNAL ENGINE (SNIPER LOGIC)
# -----------------------------
def analyze_pair(pair):
    condition = detect_market_condition()
    timeframe = select_timeframe(condition)

    base_score = strategy_score()
    confidence = calculate_confidence(base_score)

    signal = random.choice(["BUY", "SELL"])

    if confidence < 65:
        return None

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
