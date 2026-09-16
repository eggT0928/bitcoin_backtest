"""Frozen BTC study: causal signals, self-financing holdings and common accounting."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import os

import numpy as np
import pandas as pd
import legacy_signals as legacy

YEAR = 365.25
ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / 'research/data/btc_usd_daily.csv'
LABELS = {key: value['label'] for key, value in legacy.STRATEGIES.items()}
LABELS.update(buy_hold='BTC Buy & Hold', weekly_price='연구: 주간 가격·120일선',
              monthly_10m='연구: 월말 10개월선', weekly_price_vol='연구: 주간 가격·변동성40%')
NEW_KEYS = ['weekly_price', 'monthly_10m', 'weekly_price_vol']
PERIODS = {'전체기간': ('2015-08-02', None), '초기 관측 2015–2016': ('2015-08-02', '2016-12-31'),
           '2017–2018 사이클': ('2017-01-01', '2018-12-31'), '2019 전환기': ('2019-01-01', '2019-12-31'),
           '2020–2022 사이클': ('2020-01-01', '2022-12-31'), '2023 이후': ('2023-01-01', None),
           '사후적 holdout 2019 이후': ('2019-01-01', None)}


def validate_prices(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame[['close']].copy()
    idx = pd.DatetimeIndex(pd.to_datetime(out.index))
    if idx.tz is not None:
        idx = idx.tz_convert('UTC').tz_localize(None)
    out.index = idx
    if not idx.is_unique or not idx.is_monotonic_increasing or not idx.equals(idx.normalize()):
        raise ValueError('가격 날짜는 중복 없는 오름차순 UTC 일자여야 합니다.')
    if len(idx) < 2 or not idx.equals(pd.date_range(idx[0], idx[-1], freq='D')):
        raise ValueError('BTC 일봉이 누락되었습니다. 결측일을 임의로 채우지 않습니다.')
    if not np.isfinite(out.close.to_numpy()).all() or (out.close <= 0).any():
        raise ValueError('비정상 가격이 있습니다.')
    out.index.name = 'date'
    return out


def load_snapshot() -> pd.DataFrame:
    return validate_prices(pd.read_csv(DATA_PATH, index_col=0, parse_dates=True))


def download_prices(provider='coinmetrics') -> pd.DataFrame:
    if provider == 'coinmetrics':
        import io
        import requests
        url = 'https://raw.githubusercontent.com/coinmetrics/data/master/csv/btc.csv'
        response = requests.get(url, timeout=45, verify=os.environ.get('BTC_CA_BUNDLE', True))
        response.raise_for_status()
        raw = pd.read_csv(io.StringIO(response.text), usecols=['time','PriceUSD'])
        raw = raw.set_index(pd.to_datetime(raw.time)).rename(columns={'PriceUSD':'close'})[['close']]
        cutoff = pd.Timestamp.now(tz='UTC').normalize().tz_localize(None)
        raw = raw.loc[(raw.index >= '2014-09-17') & (raw.index < cutoff)]
        # Only remove trailing unavailable prices; gaps inside the sample remain an error.
        last = raw.close.last_valid_index()
        if last is None:
            raise ValueError('Coin Metrics 유효 가격이 없습니다.')
        out = validate_prices(raw.loc[:last])
        out.attrs.update(provider='Coin Metrics Community archive / BTC PriceUSD', source_url=url,
                         raw_sha256=hashlib.sha256(response.content).hexdigest())
        return out
    if provider != 'yahoo':
        raise ValueError('지원하지 않는 데이터 공급자입니다.')
    import yfinance as yf
    from curl_cffi import requests
    cutoff = pd.Timestamp.now(tz='UTC').normalize().tz_localize(None)
    session = requests.Session(impersonate='chrome', verify=os.environ.get('BTC_CA_BUNDLE', True))
    raw = yf.download('BTC-USD', start='2014-09-01', end=cutoff.strftime('%Y-%m-%d'),
                      auto_adjust=True, progress=False, threads=False, session=session)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    if raw.empty:
        raise ValueError('Yahoo Finance에서 완결 일봉을 받지 못했습니다.')
    raw = raw.rename(columns={'Close': 'close'})
    raw.index = pd.to_datetime(raw.index)
    if raw.index.tz is not None:
        raw.index = raw.index.tz_convert('UTC').tz_localize(None)
    out = validate_prices(raw.loc[raw.index < cutoff, ['close']])
    out.attrs['provider'] = 'Yahoo Finance / yfinance BTC-USD'
    return out


def save_snapshot(prices: pd.DataFrame) -> dict:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    prices.to_csv(DATA_PATH, float_format='%.10f')
    meta = dict(provider=prices.attrs.get('provider', 'unspecified'),
                daily_basis='Provider UTC daily labels; unfinished UTC day excluded',
                fetched_at_utc=pd.Timestamp.now(tz='UTC').isoformat(),
                first_date=str(prices.index[0].date()), last_date=str(prices.index[-1].date()),
                rows=len(prices), sha256=hashlib.sha256(DATA_PATH.read_bytes()).hexdigest())
    meta.update({key:value for key,value in prices.attrs.items() if key != 'provider'})
    DATA_PATH.with_suffix('.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    return meta


@dataclass
class Signals:
    targets: pd.DataFrame
    rebalance: pd.DataFrame
    ready: pd.Timestamp


def make_signals(prices: pd.DataFrame, base_ma=120, monthly_window=10,
                 vol_target=0.40, vol_window=60, weekday=6) -> Signals:
    close = prices.close
    df = legacy.add_moving_averages(prices)
    # Preserve original ma120 column/API, substituting its horizon only for preregistered diagnostics.
    df['ma120'] = close.rolling(base_ma).mean()
    targets = pd.DataFrame(index=prices.index)
    for key, config in legacy.STRATEGIES.items():
        if key == 'weekly' and weekday != 6:
            freq = {1: 'W-TUE', 4: 'W-FRI'}[weekday]
            weekly = df.resample(freq).last().dropna(subset=['close'])
            sig = legacy.add_cross_signals(weekly)
            pos = legacy.calculate_event_position(sig, 'partial', 0.0)
            targets[key] = pos.reindex(df.index, method='ffill').fillna(0.0)
        else:
            targets[key] = legacy.calculate_strategy_position(df, config)
    targets['buy_hold'] = 1.0
    decision = pd.Series(prices.index.dayofweek == weekday, index=prices.index)
    ma = df.ma120
    direction = pd.Series(np.where(close > ma, 1., np.where(close < ma, 0., np.nan)), index=close.index)
    weekly = direction.where(decision).ffill().fillna(0.)
    targets['weekly_price'] = weekly

    # Select only actual complete calendar months, never label an incomplete month as future month-end.
    month_close = close.loc[close.index.is_month_end]
    if close.index[0].day != 1:
        month_close = month_close.loc[month_close.index.to_period('M') != close.index[0].to_period('M')]
    month_ma = month_close.rolling(monthly_window).mean()
    monthly = pd.Series(np.where(month_close > month_ma, 1., np.where(month_close < month_ma, 0., np.nan)), index=month_close.index)
    targets['monthly_10m'] = monthly.ffill().reindex(close.index, method='ffill').fillna(0.)
    vol = close.pct_change().rolling(vol_window).std(ddof=1) * np.sqrt(YEAR)
    scale = (vol_target / vol).clip(upper=1.)
    targets['weekly_price_vol'] = (weekly * scale).where(decision).ffill().fillna(0.)
    rebalance = targets.diff().abs().gt(1e-12)
    rebalance['weekly_price_vol'] = decision & vol.notna() & ma.notna()
    ready_candidates = [ma.first_valid_index(), month_ma.first_valid_index(), vol.first_valid_index()]
    if any(x is None for x in ready_candidates):
        raise ValueError('모든 후보의 공통 준비기간을 충족하지 못했습니다.')
    ready = max(ready_candidates) + pd.Timedelta(days=2)
    return Signals(targets, rebalance, ready)


def _trade(cash, units, price, target, fee):
    """Target is a fraction of NAV *after* paying transaction costs."""
    nav = cash + units * price
    difference = target * nav - units * price
    sign = np.sign(difference)
    amount = difference / (1. + sign * fee * target)
    if abs(amount) < nav * 1e-12:
        return cash, units, 0., 0., 0
    cost = fee * abs(amount)
    return cash - amount - cost, units + amount / price, abs(amount) / nav, cost / nav, int(sign)


def simulate(prices: pd.DataFrame, target: pd.Series, rebalance: pd.Series,
             fee=0.001, start=None, end=None, delay=1) -> pd.DataFrame:
    """Fresh cash at start-1 close; first return includes the opening fee. No terminal sale."""
    if not 0 <= fee < 1 or delay < 1 or not isinstance(delay, int):
        raise ValueError('비용/실행 지연 설정이 잘못되었습니다.')
    target = target.reindex(prices.index)
    rebalance = rebalance.reindex(prices.index)
    if target.isna().any() or rebalance.isna().any() or not target.between(0, 1).all():
        raise ValueError('유효하지 않은 신호/목표비중입니다.')
    dates = prices.loc[start:end].index
    if len(dates) == 0:
        raise ValueError('선택 기간에 데이터가 없습니다.')
    first = prices.index.get_loc(dates[0])
    last = prices.index.get_loc(dates[-1])
    if first < delay + 1:
        raise ValueError('시작 이전 실행 준비 데이터가 부족합니다.')
    px = prices.close.to_numpy()
    tg = target.to_numpy()
    rb = rebalance.to_numpy(dtype=bool)
    anchor = first - 1
    cash, units, initial_turn, initial_fee, initial_side = _trade(1., 0., px[anchor], tg[anchor-delay], fee)
    previous_nav = 1.
    rows = []
    for i in range(first, last + 1):
        prev_value = cash + units * px[i-1]
        applied_weight = units * px[i-1] / prev_value
        turnover, paid, side = 0., 0., 0
        if rb[i-delay]:
            cash, units, turnover, paid, side = _trade(cash, units, px[i], tg[i-delay], fee)
        nav = cash + units * px[i]
        initial = i == first
        rows.append((nav / previous_nav - 1., nav, units * px[i] / nav, applied_weight,
                     turnover + (initial_turn if initial else 0), paid + (initial_fee if initial else 0),
                     int(side != 0) + (int(initial_side != 0) if initial else 0), side,
                     tg[i], tg[i-delay], cash, units))
        previous_nav = nav
    return pd.DataFrame(rows, index=dates, columns=['return', 'equity', 'weight', 'applied_weight',
                         'turnover', 'fee_fraction', 'orders', 'side', 'signal_target', 'executed_target', 'cash', 'btc_units'])


def run_all(prices, signals=None, fee=0.001, start=None, end=None, delay=1):
    signals = signals or make_signals(prices)
    start = max(pd.Timestamp(start or '2015-08-02'), signals.ready + pd.Timedelta(days=delay-1))
    return {key: simulate(prices, signals.targets[key], signals.rebalance[key], fee, start, end, delay)
            for key in signals.targets}


def slice_path(path, start=None, end=None):
    out = path.loc[start:end].copy()
    if out.empty:
        return out
    out['equity'] = (1. + out['return']).cumprod()
    return out


def drawdown(path):
    equity = path.equity
    return equity / equity.cummax().clip(lower=1.) - 1.


def recovery_stats(equity):
    peak = 1.
    peak_date = equity.index[0] - pd.Timedelta(days=1)
    durations = []
    underwater = False
    current_days = 0
    for date, value in equity.items():
        if value >= peak * (1 - 1e-12):
            if underwater:
                durations.append((date - peak_date).days)
            peak = max(peak, value)
            peak_date = date
            underwater = False
        else:
            underwater = True
    if underwater:
        current_days = (equity.index[-1] - peak_date).days
    return {'recovery_max_days': max(durations) if durations else np.nan,
            'recovery_mean_days': float(np.mean(durations)) if durations else np.nan,
            'recovered_episodes': len(durations), 'unrecovered_days': current_days,
            'underwater_max_days': max(durations + [current_days])}


def metrics(path):
    if path.empty:
        return {}
    returns = path['return']
    years = len(path) / YEAR
    cagr = path.equity.iloc[-1] ** (1 / years) - 1
    dd = drawdown(path)
    vol = returns.std(ddof=1) * np.sqrt(YEAR)
    downside = np.sqrt(np.mean(np.minimum(returns, 0.) ** 2)) * np.sqrt(YEAR)
    ui = np.sqrt(np.mean(dd ** 2))
    def ratio(a, b):
        return a / b if b > 1e-15 else np.nan
    orders = path.loc[path.side != 0, 'side']
    reverse = (orders * orders.shift(1) < 0) & (orders.index.to_series().diff().dt.days <= 14)
    return dict(CAGR=cagr, MDD=dd.min(), volatility=vol,
                Sharpe=ratio(returns.mean()*YEAR, vol), Sortino=ratio(returns.mean()*YEAR, downside),
                Ulcer=ui, UPI=ratio(cagr, ui), Calmar=ratio(cagr, abs(dd.min())),
                mean_weight=path.applied_weight.mean(), mean_cash=1-path.applied_weight.mean(),
                orders=int(path.orders.sum()), turnover_pa=path.turnover.sum()/years,
                fee_sum=path.fee_fraction.sum(), final_multiple=path.equity.iloc[-1],
                reversal_14d_count=int(reverse.sum()), reversal_14d_rate=reverse.mean() if len(reverse) else 0.,
                **recovery_stats(path.equity))


def metric_table(paths):
    return pd.DataFrame({key: metrics(path) for key, path in paths.items() if not path.empty}).T.rename_axis('strategy')


def period_table(paths):
    frames = []
    for period, (start, end) in PERIODS.items():
        frame = metric_table({k: slice_path(v, start, end) for k, v in paths.items()})
        frame.insert(0, 'period', period)
        frames.append(frame.reset_index())
    return pd.concat(frames, ignore_index=True)


def annual_returns(paths):
    return pd.DataFrame({key: path['return'].groupby(path.index.year).apply(lambda x: (1+x).prod()-1)
                         for key, path in paths.items()}).rename_axis('year')
