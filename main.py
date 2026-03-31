import requests
import time
import os
import threading
from datetime import datetime, timedelta, timezone
from flask import Flask

# =========================
# الإعدادات الأساسية
# =========================
TWELVEDATA_KEY = "867e160b02b3402e8ddf705c03544487"
TOKEN = "8212195518:AAHqa5jb5h_el4ohPMc0pAxqRAQCc7kUeJI"
CHAT_IDS = ["5652097199", "8214327595"] 

# إعدادات العملات وإدارة المخاطر (3 ربح مقابل 1 خسارة)
SYMBOLS_CONFIG = {
    "EUR/USD": {"sl_percent": 0.0003, "tp_percent": 0.0009},
    "GBP/USD": {"sl_percent": 0.0003, "tp_percent": 0.0009},
    "EUR/GBP": {"sl_percent": 0.0002, "tp_percent": 0.0006},
    "XAU/USD": {"sl_percent": 0.0005, "tp_percent": 0.0015}
}

active_trades = {}

# =========================
# الدوال المساعدة
# =========================
def send_msg(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    for cid in CHAT_IDS:
        try: 
            requests.post(url, data={"chat_id": cid, "text": text, "parse_mode": "Markdown"})
        except: 
            print("❌ خطأ في إرسال رسالة تليجرام", flush=True)

def get_data(symbol):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval=5min&outputsize=100&apikey={TWELVEDATA_KEY}"
    try:
        res = requests.get(url).json()
        if "values" not in res: return None, [], [], []
        data = res["values"]
        closes = [float(d["close"]) for d in data][::-1]
        highs = [float(d["high"]) for d in data][::-1]
        lows = [float(d["low"]) for d in data][::-1]
        return closes, highs, lows
    except: 
        return None, [], [], []

def rsi(data, period=14):
    if len(data) < period + 1: return 50
    deltas = [data[i] - data[i-1] for i in range(1, len(data))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses = [abs(d) if d < 0 else 0 for d in deltas[-period:]]
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    if avg_l == 0: return 100
    rs = avg_g / avg_l
    return 100 - (100 / (1 + rs))

def strategy(symbol, closes, highs, lows):
    price, rsi_val = closes[-1], rsi(closes)
    ma100 = sum(closes[-100:]) / 100
    recent_high, recent_low = max(highs[-50:]), min(lows[-50:])
    fib_618 = recent_high - ((recent_high - recent_low) * 0.618)
    config = SYMBOLS_CONFIG[symbol]

    # شروط الشراء (BUY)
    if price > ma100 and price <= fib_618 * 1.0005 and rsi_val < 45:
        return "BUY", price, price * (1 - config['sl_percent']), price * (1 + config['tp_percent'])
    
    # شروط البيع (SELL)
    if price < ma100 and price >= fib_618 * 0.9995 and rsi_val > 55:
        return "SELL", price, price * (1 + config['sl_percent']), price * (1 - config['tp_percent'])
    
    return None, None, None, None

# =========================
# المحرك الأساسي (Logic)
# =========================
def run_bot():
    print("🚀 تم تشغيل المحرك بنظام توقيت سوريا (10ص - 9م)...", flush=True)
    send_msg("✅ *تم تحديث نظام إدارة المخاطر!*\n\n- النسبة الحالية: 3 ربح مقابل 1 خسارة\n- نظام المومنتوم وفيبوناتشي: فعال\n- رسائل التأكيد (كل 5 دقائق): مفعلة")

    last_check = 0
    while True:
        try:
            # توقيت سوريا الحالي (GMT+3)
            syria_now = datetime.now(timezone(timedelta(hours=3)))
            current_hour = syria_now.hour
            
            # العمل فقط من الساعة 10 صباحاً حتى 9 مساءً
            if 10 <= current_hour < 21:
                curr_ts = time.time()
                
                # تنفيذ الفحص كل 5 دقائق (300 ثانية)
                if curr_ts - last_check >= 300 or last_check == 0:
                    # إرسال رسالة التأكيد التي طلبتها
                    send_msg(f"📡 *البوت يفحص السوق الآن (5M)...*\n⏰ توقيت سوريا: {syria_now.strftime('%H:%M')}")
                    print(f"🔍 [{syria_now.strftime('%H:%M')}] جولة فحص جارية...", flush=True)
                    
                    for symbol in SYMBOLS_CONFIG.keys():
                        closes, highs, lows = get_data(symbol)
                        if not closes: continue
                        
                        # إدارة الصفقات المفتوحة
                        if symbol in active_trades:
                            trade = active_trades[symbol]
                            current_p = closes[-1]
                            result = None
                            
                            if trade['type'] == "BUY":
                                if current_p >= trade['tp']: result = "WIN ✅"
                                elif current_p <= trade['sl']: result = "LOSS ❌"
                            else:
                                if current_p <= trade['tp']: result = "WIN ✅"
                                elif current_p >= trade['sl']: result = "LOSS ❌"
                            
                            if result:
                                send_msg(f"🏁 *إغلاق صفقة:* `{symbol}`\nالنتيجة: {result}")
                                del active_trades[symbol]
                        
                        # البحث عن فرص جديدة
                        else:
                            sig, ent, sl, tp = strategy(symbol, closes, highs, lows)
                            if sig:
                                send_msg(f"🔥 *إشارة {sig} جديدة*\nالزوج: `{symbol}`\nدخول: `{round(ent, 5)}`\nالهدف: `{round(tp, 5)}` (3:1)")
                                active_trades[symbol] = {"type": sig, "tp": tp, "sl": sl}
                    
                    last_check = curr_ts
            else:
                # خارج ساعات العمل: البوت صامت في تليجرام، ويكتب في الـ Logs فقط كل ساعة
                if syria_now.minute == 0 and syria_now.second < 40:
                    print(f"😴 وضع الاستراحة (توقيت سوريا: {syria_now.strftime('%H:%M')})", flush=True)
            
            time.sleep(30) # التحقق من الوقت كل 30 ثانية
            
        except Exception as e:
            print(f"⚠️ خطأ مفاجئ: {e}", flush=True)
            time.sleep(10)

# =========================
# تشغيل سيرفر الويب (Render)
# =========================
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is Active and Running"

if __name__ == "__main__":
    # تشغيل البوت في خيط منفصل
    threading.Thread(target=run_bot).start()
    # تشغيل Flask لتجنب إيقاف السيرفر من Render
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
