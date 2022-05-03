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


# Assumes _levels is sorted
def getLevelRange(_price, _levels):
    level = bisect_left(_levels, _price)

    if level == 0:
        return [_price, _levels[0]]
    if level == len(_levels):
        return [_levels[-1], _price]

    lowerLevel = _levels[level - 1]
    upperLevel = _levels[level]

    return [lowerLevel, upperLevel]


def alertLessThan(_tickers_less_than_level):
    # Get current prices
    df = pd.DataFrame(client.get_all_tickers())
    tickers = list(_tickers_less_than_level.keys())
    df = df.loc[df['symbol'].isin(tickers)]
    df = df.reset_index()
    df['price'] = pd.to_numeric(df['price'])
    
    # Scan for price <= level
    for index in df.index:
        ticker = df['symbol'][index]
        price = df['price'][index]
        level = _tickers_less_than_level[df['symbol'][index]]
        if price <= level:
            hook.send(f'Test alerT: {ticker} is below {level} at {price} on {datetime.datetime.now()}')
            print(f'{ticker} is below {level} at {price} on {datetime.datetime.now()}')
            _tickers_less_than_level.pop(ticker)
    
    return


# tickers_less_than_level = {
#     'BTCUSDT' : 38000,
#     'ETHUSDT' : 38000,
# }

tickers_to_levels = {
    'BTCUSDT' : [38000, 38100, 38200, 38300, 38400, 38600, 38700, 38800, 38900, 39000],
    'ETHUSDT' : [2500, 2600, 2700, 2800, 2900, 3000],
}

tickers_to_current_range = {

}

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

    # If not in tickers_to_current_range then add 
    if ticker not in tickers_to_current_range:
        print('Added')
        tickers_to_current_range[ticker] = getLevelRange(price, levels)

    # Detect if in new range
    elif tickers_to_current_range[ticker] != getLevelRange(price, levels):
        print('New level', ticker, getLevelRange(price, levels)) 

print('current ranges:',tickers_to_current_range)
print('levels:', tickers_to_levels)


# print(df)

