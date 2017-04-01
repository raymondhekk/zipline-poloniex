# -*- coding: utf-8 -*-
"""
Zipline bundle for Poloniex exchange
"""
import logging
from datetime import time, timedelta

from pytz import timezone
import pandas as pd
from zipline.utils.calendars import TradingCalendar, register_calendar
from zipline.data.bundles import register

from .api import get_currencies, get_trade_hist

__author__ = "Florian Wilhelm"
__copyright__ = "Florian Wilhelm"
__license__ = "new-bsd"

_logger = logging.getLogger(__name__)


class Pairs(object):
    """Record object holding most common US-$ / crypto-currency pairs
    """
    usdt_btc = 'USDT_BTC'
    usdt_eth = 'USDT_ETH'
    usdt_dash = 'USDT_DASH'
    usdt_etc = 'USDT_ETC'
    usdt_xmr = 'USDT_XMR'
    usdt_zec = 'USDT_ZEC'
    usdt_xrp = 'USDT_XRP'
    usdt_ltc = 'USDT_LTC'
    usdt_rep = 'USDT_REP'
    usdt_nxt = 'USDT_NXT'
    usdt_str = 'USDT_STR'


def write_assets(asset_db_writer, asset_pairs):
    """Fetch and write given asset pairs

    Args:
        asset_db_writer: zipeline's asset_db_writer object
        asset_pairs (list): list of asset pairs

    Returns:
        dict: dictionary of symbol ids to asset pair name
    """
    asset_pair_map = {pair.split("_")[1]: pair for pair in asset_pairs}
    all_assets = get_currencies()
    asset_df = all_assets.ix[asset_pair_map.keys()].reset_index()
    asset_df = asset_df[['index', 'name']].rename(
        columns={'index': 'symbol', 'name': 'asset_name'})
    asset_db_writer.write(equities=asset_df)
    asset_map = asset_df['symbol'].to_dict()
    return {k: asset_pair_map[v] for k, v in asset_map.items()}


def make_candle_stick(trades):
    """Make a candle stick like chart

    Args:
        trades (pandas.DataFrame): dataframe containing trades

    Returns:
        pandas.DataFrame: chart data
    """
    freq = '1T'
    volume = trades['total'].resample(freq).sum()
    volume = volume.fillna(0)
    high = trades['rate'].resample(freq).max()
    low = trades['rate'].resample(freq).min()
    open = trades['rate'].resample(freq).first()
    close = trades['rate'].resample(freq).last()
    # ToDo: Maybe remove NA rows
    return pd.DataFrame(dict(open=open,
                             high=high,
                             low=low,
                             close=close,
                             volume=volume))


def fetch_trades(asset_pair, start, end):
    """Helper function to fetch trades for a single asset pair

    Args:
        asset_pair: name of the asset pair
        start (pandas.Timestamp): start of period
        end (pandas.Timestamp): end of period

    Returns:
        pandas.DataFrame: dataframe containing trades of asset
    """
    df = get_trade_hist(asset_pair, start, end)
    df['date'] = pd.to_datetime(df['date'])
    df = df.set_index('date')
    return df


def prepare_data(start, end, sid_map, cache):
    """Retrieve and prepare trade data for ingestion

    Args:
        start (pandas.Timestamp): start of period
        end (pandas.Timestamp): end of period
        sid_map (dict): mapping from symbol id to asset pair name
        cache: cache object as provided by zipline

    Returns:
        generator of symbol id and dataframe tuples
    """
    def get_key(sid, day):
        return "{}_{}".format(sid, day.strftime("%Y-%m-%d"))

    for sid, asset_pair in sid_map.items():
        for day in pd.date_range(start, end, freq='D', closed='left'):
            key = get_key(sid, day)
            if key not in cache:
                next_day = day + timedelta(days=1, seconds=-1)
                trades = fetch_trades(asset_pair, day, next_day)
                cache[key] = make_candle_stick(trades)
            yield sid, cache[key]


def create_bundle(asset_pairs, start=None, end=None):
    """Create a bundle ingest function

    Args:
        asset_pairs (list): list of asset pairs
        start (pandas.Timestamp): start of trading period
        end (pandas.Timestamp): end of trading period

    Returns:
        ingest function needed by zipline's register.
    """
    def ingest(environ,
               asset_db_writer,
               minute_bar_writer,
               daily_bar_writer,
               adjustment_writer,
               calendar,
               start_session,
               end_session,
               cache,
               show_progress,
               output_dir,
               # pass these as defaults to make them 'nonlocal' in py2
               start=start,
               end=end):
        if start is None:
            start = start_session
        if end is None:
            end = end_session

        sid_map = write_assets(asset_db_writer, asset_pairs)
        data = prepare_data(start, end, sid_map, cache)
        minute_bar_writer.write(data, show_progress=show_progress)
    return ingest


class PoloniexCalendar(TradingCalendar):
    """Trading Calender of Poloniex Exchange
    """
    @property
    def name(self):
        return "POLONIEX"

    @property
    def tz(self):
        return timezone('UTC')

    @property
    def open_time(self):
        return time(0, 0)

    @property
    def close_time(self):
        return time(23, 59)


register_calendar('POLONIEX', PoloniexCalendar())
register(
    '.test_poloniex',
    create_bundle(
        [Pairs.usdt_eth],
        pd.Timestamp('2016-01-01', tz='utc'),
        pd.Timestamp('2016-01-31', tz='utc'),
    ),
    calendar_name='POLONIEX',
    minutes_per_day=24*60
)
