from asyncio.windows_events import NULL
import pandas as pd
import numpy as np
import talib
import schedule, time, datetime
from binance.client import Client
from dhooks import Webhook
from bisect import bisect_left

import config

client = Client(config.API_KEY, config.API_SECRET)
hook = Webhook(config.HOOK)
pd.options.mode.chained_assignment = None  # default='warn'


# Dictionary for time_intervals -> # of minutes
time_interval_to_minutes = {
    '1m' : 1,
    '3m' : 3,
    '5m' : 5,
    '15m' : 15,
    '30m' : 30,
    '1h' : 60,
    '2h' : 120,
    '4h' : 240,
    '6h' : 360,
    '8h' : 480,
    '12h' : 720,
    '1d' : 1440,
    '3d' : 4320,
    '1w' : 10080,
    '1M' : 40320
}


# Get candlestick data 
def getData(_ticker, _time_interval):
    btc1h = np.array(client.get_historical_klines(_ticker, _time_interval, '1 day ago UTC'))
    df = pd.DataFrame(btc1h[:-1, :6], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].apply(pd.to_numeric)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    # print(df)
    return df


# Assumes _levels is sorted from least to greatest
def getLevelRange(_price, _levels):
    level = bisect_left(_levels, _price)

    if level == 0:
        return [_price, _levels[0]]
    if level == len(_levels):
        return [_levels[-1], _price]

    lowerLevel = _levels[level - 1]
    upperLevel = _levels[level]

    return [lowerLevel, upperLevel]


# Get RSI
def calculateRSI(_df, _rsi_period):
    rsi = talib.RSI(_df.close, timeperiod=_rsi_period)
    _df['rsi'] = rsi
    # print(df)
    return _df


# Get ATR
def calculateATR(_df, _atr_period):
    _df['atr'] = talib.ATR(_df['high'], _df['low'], _df['close'], timeperiod=_atr_period)
    # print(_df)
    return _df


# Get supertrend
# warning: https://stackoverflow.com/questions/20625582/how-to-deal-with-settingwithcopywarning-in-pandas
def calculateSupertrend(_df, _atr_period, _atrlength):
    # Calculate atr & upper/lower bands
    _df = calculateATR(_df, _atr_period)
    hl2 = (_df['high'] + _df['low']) / 2
    _df['upperband'] = hl2 + (_atrlength * _df['atr'])
    _df['lowerband'] = hl2 - (_atrlength * _df['atr'])
    _df['uptrend'] = NULL

    # Check for supertrend conditions
    for current in range(1, len(_df.index)):
        previous = current - 1

        if _df['close'][current] > _df['upperband'][previous]:
            _df['uptrend'][current] = True
        elif _df['close'][current] < _df['lowerband'][previous]:
            _df['uptrend'][current] = False
        else:
            _df['uptrend'][current] = _df['uptrend'][previous]

            if _df['uptrend'][current] and _df['lowerband'][current] < _df['lowerband'][previous]:
                _df['lowerband'][current] = _df['lowerband'][previous]

            if not _df['uptrend'][current] and _df['upperband'][current] > _df['upperband'][previous]:
                _df['upperband'][current] = _df['upperband'][previous]

    # print(_df)
    return _df


def supertrendStrategy(_ticker, _time_interval, _rsi_period, _atr_period, _atr_length):
    raw_data = getData(_ticker, _time_interval)
    supertrend_data = calculateRSI(raw_data, _rsi_period)
    supertrend_data = calculateSupertrend(supertrend_data, _atr_period, _atr_length)
    last_candle = len(supertrend_data.index) - 1
    last_last_candle = last_candle - 1

    # Buy signal: supertrend is green (flipped from red) && rsi < 31 in last 5 candles 
    if supertrend_data['uptrend'][last_last_candle] == False and supertrend_data['uptrend'][last_candle] == True:
        if (supertrend_data['rsi'].tail(6) < 31).any():
            close_price = supertrend_data['close'][last_candle]
            hook.send(f'SUPERTREND ALERT: {_ticker} {_time_interval} buy signal detected at {close_price} on {datetime.datetime.now()}')
            print(f'SUPERTREND ALERT: {_ticker} {_time_interval} buy signal detected at {close_price} on {datetime.datetime.now()}')
            # Sleep until next candle 
            time.sleep((time_interval_to_minutes[_time_interval] * 60) - 55)

    # Sell signal: supertrend is red (flipped from green) && rsi > 69 in last 5 candles
    elif supertrend_data['uptrend'][last_last_candle] == True and supertrend_data['uptrend'][last_candle] == False:
        if (supertrend_data['rsi'].tail(6) > 69).any():
            close_price = supertrend_data['close'][last_candle]
            hook.send(f'SUPERTREND ALERT: {_ticker} {_time_interval} sell signal detected at {close_price} on {datetime.datetime.now()}')
            print(f'SUPERTREND ALERT: {_ticker} {_time_interval} sell signal detected at {close_price} on {datetime.datetime.now()}')
            # Sleep until next candle 
            time.sleep((time_interval_to_minutes[_time_interval] * 60) - 55)


def priceLevelAlerts():
    # Get current prices
    df = pd.DataFrame(client.get_all_tickers())
    tickers = list(tickers_to_levels.keys())
    df = df.loc[df['symbol'].isin(tickers)]
    df = df.reset_index()
    df['price'] = pd.to_numeric(df['price'])

    # Scan for changes in levels
    for index in df.index:
        ticker = df['symbol'][index]
        price = df['price'][index]
        levels = tickers_to_levels[df['symbol'][index]]
        currentRange = getLevelRange(price, levels)

        # Initial deployment: if not in tickers_to_current_range then add 
        if ticker not in tickers_to_current_range:
            tickers_to_current_range[ticker] = currentRange
            hook.send(f'Monitoring {ticker} @ {levels}')
            print(f'Monitoring {ticker} @ {levels}')

        # Detect if in new range
        elif tickers_to_current_range[ticker] != currentRange:
            tickers_to_current_range[ticker] = currentRange
            hook.send(f'PRICE LEVEL ALERT: {ticker} is {price} in {currentRange} on {datetime.datetime.now()}')
            print(f'PRICE LEVEL ALERT: {ticker} is {price} in {currentRange} on {datetime.datetime.now()}') 


# main
hook.send('Nwabot restarted')

# must be ascending order
tickers_to_levels = {
    'BTCUSDT' : [37200, 39200, 40000],
    'AXSUSDT' : [28, 32],
}

tickers_to_current_range = {}

schedule.every(10).seconds.do(priceLevelAlerts)

schedule.every(1).minute.at(':00').do(supertrendStrategy,
    _ticker = 'BTCUSDT',
    _time_interval = Client.KLINE_INTERVAL_15MINUTE,
    _rsi_period = 7,
    _atr_period = 5,
    _atr_length = 1.5
)

while True:
    schedule.run_pending()
    time.sleep(1)