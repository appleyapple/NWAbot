# from asyncio.windows_events import NULL
import pandas as pd
import numpy as np
import talib
import schedule, time, datetime
from binance.client import Client
from dhooks import Webhook

import config

client = Client(config.API_KEY, config.API_SECRET)
hook = Webhook(config.HOOK)
pd.options.mode.chained_assignment = None  # default='warn'

# Get candlestick data 
def getData(_ticker, _time_interval):
    btc1h = np.array(client.get_historical_klines(_ticker, _time_interval, '1 day ago UTC'))
    df = pd.DataFrame(btc1h[:-1, :6], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df[['open', 'high', 'low', 'close', 'volume']] = df[['open', 'high', 'low', 'close', 'volume']].apply(pd.to_numeric)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    # print(df)
    return df


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

    # Buy signal: supertrend is green (flipped from red) && rsi < 31 in last timeframe * 5 
    if supertrend_data['uptrend'][last_last_candle] == False and supertrend_data['uptrend'][last_candle] == True:
        if (supertrend_data['rsi'].tail(5) < 31).any():
            close_price = supertrend_data['close'][last_candle]
            hook.send(f'Test alert: {_ticker} {_time_interval} buy signal detected at {close_price} on {datetime.datetime.now()}')
            print(f'{_ticker} {_time_interval} buy signal detected at {close_price} on {datetime.datetime.now()}')

    # Sell signal: supertrend is red (flipped from green) && rsi > 69 in last timeframe * 5 
    elif supertrend_data['uptrend'][last_last_candle] == True and supertrend_data['uptrend'][last_candle] == False:
        if (supertrend_data['rsi'].tail(5) > 69).any():
            close_price = supertrend_data['close'][last_candle]
            hook.send(f'Test alert: {_ticker} {_time_interval} sell signal detected at {close_price} on {datetime.datetime.now()}')
            print(f'{_ticker} {_time_interval} sell signal detected at {close_price} on {datetime.datetime.now()}')

    # print(supertrend_data)


# main
hook.send('Monitoring BTCUSDT 15m supertrend+rsi...')

schedule.every(1).minute.at(':00').do(supertrendStrategy,
    _ticker = 'BTCUSDT',
    _time_interval = Client.KLINE_INTERVAL_15MINUTE,
    _time_period = '1 day ago UTC',
    _rsi_period = 7,
    _atr_period = 5,
    _atr_length = 1.5
)

while True:
    schedule.run_pending()
    time.sleep(1)