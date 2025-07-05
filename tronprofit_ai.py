import time
import requests
import hmac
import hashlib
import pandas as pd
import numpy as np
import os
from urllib.parse import urlencode
from dotenv import load_dotenv
from datetime import datetime

# ====== LOAD ENV VARIABLES ======
load_dotenv()
API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

# ====== CONFIGURATION ======
BASE_URL = 'https://testnet.binance.vision'
SYMBOL = 'BTCUSDT'
TRADE_QUANTITY = 0.001
TRADE_LOG_FILE = 'trade_log.csv'
PERFORMANCE_FEE_PERCENTAGE = 0.20  # 20%

# ====== AI DECISION ENGINE ======
def get_klines(symbol='BTCUSDT', interval='1h', limit=100):
    url = f'{BASE_URL}/api/v3/klines'
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}
    response = requests.get(url, params=params)
    data = response.json()
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume',
                                     'close_time', 'quote_asset_volume', 'num_trades',
                                     'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'])
    df['close'] = pd.to_numeric(df['close'])
    return df[['timestamp', 'close']]

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_ema(prices, span):
    return prices.ewm(span=span, adjust=False).mean()

def calculate_macd(prices):
    ema12 = calculate_ema(prices, 12)
    ema26 = calculate_ema(prices, 26)
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    return macd_line, signal_line

def ai_decision_engine():
    df = get_klines(SYMBOL)
    df['RSI'] = calculate_rsi(df['close'])
    df['EMA12'] = calculate_ema(df['close'], 12)
    df['EMA26'] = calculate_ema(df['close'], 26)
    df['MACD'], df['Signal'] = calculate_macd(df['close'])

    latest = df.iloc[-1]
    rsi = latest['RSI']
    ema12 = latest['EMA12']
    ema26 = latest['EMA26']
    macd = latest['MACD']
    signal = latest['Signal']

    if rsi < 30 and ema12 > ema26 and macd > signal:
        return 'BUY'
    elif rsi > 70 and ema12 < ema26 and macd < signal:
        return 'SELL'
    return 'HOLD'

# ====== TRADING EXECUTION ======
def create_signature(query_string, secret):
    return hmac.new(secret.encode(), query_string.encode(), hashlib.sha256).hexdigest()

def send_order(symbol, side, quantity):
    path = '/api/v3/order'
    url = BASE_URL + path
    timestamp = int(time.time() * 1000)
    params = {
        'symbol': symbol,
        'side': side,
        'type': 'MARKET',
        'quantity': quantity,
        'timestamp': timestamp
    }
    query_string = urlencode(params)
    signature = create_signature(query_string, API_SECRET)
    headers = {"X-MBX-APIKEY": API_KEY}
    params['signature'] = signature
    response = requests.post(url, headers=headers, params=params)
    return response.json()

# ====== PROFIT TRACKING ======
def log_trade(trade_type, price):
    timestamp = datetime.utcnow().isoformat()
    entry = f"{timestamp},{trade_type},{price}\n"
    with open(TRADE_LOG_FILE,'a') as f:
        f.write(entry)

def read_last_trade():
    if not os.path.exists(TRADE_LOG_FILE):
        return None, None
    with open(TRADE_LOG_FILE, 'r') as f:
        lines = f.readlines()
        if not lines:
            return None, None
        last = lines[-1].strip().split(',')
        return last[1], float(last[2])

def calculate_profit(current_price):
    last_type, last_price = read_last_trade()
    if last_type == 'BUY':
        profit = (current_price - last_price) * TRADE_QUANTITY
        fee = profit * PERFORMANCE_FEE_PERCENTAGE
        return profit, fee
    elif last_type == 'SELL':
        profit = (last_price - current_price) * TRADE_QUANTITY
        fee = profit * PERFORMANCE_FEE_PERCENTAGE
        return profit, fee
    return 0, 0

# ====== MAIN LOOP ======
def run_bot():
    while True:
        decision = ai_decision_engine()
        print(f"AI Decision: {decision}")

        current_price = get_klines(SYMBOL).iloc[-1]['close']
        profit, fee = calculate_profit(current_price)
        print(f"Current Unrealized Profit: {profit:.4f} USDT | Your Fee: {fee:.4f} USDT")

        if decision == 'BUY':
            result = send_order(SYMBOL, 'BUY', TRADE_QUANTITY)
            print(f"Buy Order Result: {result}")
            log_trade('BUY', current_price)
        elif decision == 'SELL':
            result = send_order(SYMBOL, 'SELL', TRADE_QUANTITY)
            print(f"Sell Order Result: {result}")
            log_trade('SELL', current_price)
        else:
            print("HOLD - No trade executed.")

        time.sleep(60) # Wait 1 minute before next trade

if __name__ == "__main__":
    run_bot()
