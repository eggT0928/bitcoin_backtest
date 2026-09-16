import numpy as np
import pandas as pd
import pytest
import legacy_signals
from backtest_engine import (_trade, validate_prices, make_signals, simulate, metrics,
                             recovery_stats, slice_path, run_all)


def prices(n=900):
    rng = np.random.default_rng(81)
    index = pd.date_range('2014-09-17', periods=n)
    return pd.DataFrame({'close': 100*np.exp(np.cumsum(rng.normal(.0005, .04, n)))}, index=index)


def test_confirmed_cross_is_only_first_qualifying_day():
    state = pd.Series([False, True, True, True, False, True, True])
    assert legacy_signals.state_signal(state, 1).tolist() == [False,True,False,False,False,True,False]
    assert legacy_signals.state_signal(state, 2).tolist() == [False,False,True,False,False,False,True]


def test_cash_units_and_cost_equation():
    cash, units, turn, cost, side = _trade(1, 0, 100, .5, .001)
    nav = cash + units*100
    assert nav == pytest.approx(1-cost)
    assert units*100/nav == pytest.approx(.5)
    cash, units, turn, cost, side = _trade(cash, units, 150, 0, .001)
    assert units == pytest.approx(0)
    assert side == -1
    assert cash > 1


def test_buy_hold_charged_once_and_exact_path():
    p = prices()
    t = pd.Series(1., index=p.index)
    path = simulate(p, t, t.diff().abs().gt(0), start=p.index[400], fee=.001)
    expected = p.close.iloc[-1]/p.close.iloc[399]/1.001
    assert path.equity.iloc[-1] == pytest.approx(expected)
    assert path.orders.sum() == 1
    assert path.turnover.sum() == pytest.approx(1/1.001)
    np.testing.assert_allclose(path.weight, 1., atol=1e-12)


def test_one_full_close_delay_and_fees_on_execution():
    p = pd.DataFrame({'close': [100.,100.,100.,200.,400.,800.]}, index=pd.date_range('2020-01-01', periods=6))
    t = pd.Series([0.,0.,0.,1.,1.,1.], index=p.index)
    path = simulate(p, t, t.diff().abs().gt(0), start=p.index[2], fee=.001)
    assert path.loc[p.index[3], 'equity'] == 1
    assert path.loc[p.index[4], 'equity'] == pytest.approx(1/1.001)
    assert path.loc[p.index[5], 'equity'] == pytest.approx(2/1.001)
    assert path.loc[p.index[4], 'orders'] == 1


def test_partial_holdings_drift_without_free_rebalancing():
    p = pd.DataFrame({'close': [100.,100.,100.,200.,400.]}, index=pd.date_range('2020-01-01', periods=5))
    t = pd.Series(.5, index=p.index)
    path = simulate(p, t, t.diff().abs().gt(0), start=p.index[2], fee=0)
    assert path.equity.iloc[-1] == pytest.approx(2.5)
    assert path.weight.iloc[-1] == pytest.approx(.8)
    assert path.orders.sum() == 1


@pytest.mark.parametrize('n', [425, 518, 679])
def test_every_signal_is_prefix_invariant(n):
    p = prices()
    full, prefix = make_signals(p), make_signals(p.iloc[:n])
    pd.testing.assert_frame_equal(full.targets.iloc[:n], prefix.targets)
    pd.testing.assert_frame_equal(full.rebalance.iloc[:n], prefix.rebalance)


def test_future_price_change_cannot_change_past_returns():
    p = prices()
    changed = p.copy()
    changed.iloc[700:, 0] *= np.linspace(1.1, 3., len(changed)-700)
    a, b = run_all(p), run_all(changed)
    for k in a:
        pd.testing.assert_frame_equal(a[k].loc[:p.index[699]], b[k].loc[:p.index[699]])


def test_partial_month_and_week_never_used_early():
    s = make_signals(prices(450))
    monthly_changes = s.targets.monthly_10m.diff().fillna(0).ne(0)
    assert s.targets.index[monthly_changes].is_month_end.all()
    weekly_changes = s.targets.weekly_price.diff().fillna(0).ne(0)
    assert (s.targets.index[weekly_changes].dayofweek == 6).all()


def test_drawdown_recovery_censoring_and_sortino_definition():
    idx = pd.date_range('2020-01-01', periods=5)
    eq = pd.Series([1., .8, 1., .9, .85], index=idx)
    stats = recovery_stats(eq)
    assert stats['recovery_max_days'] == 2
    assert stats['recovery_mean_days'] == 2
    assert stats['unrecovered_days'] == 2
    assert stats['recovered_episodes'] == 1
    p = prices()
    result = next(iter(run_all(p).values()))
    m = metrics(result)
    down = np.sqrt(np.mean(np.minimum(result['return'], 0)**2))
    assert m['Sortino'] == pytest.approx(result['return'].mean()/down*np.sqrt(365.25))


def test_opening_loss_and_period_rebase():
    p = prices()
    result = run_all(p)['buy_hold']
    sub = slice_path(result, '2016-01-01', '2016-06-30')
    assert sub.equity.iloc[-1] == pytest.approx((1+sub['return']).prod())
    assert metrics(sub)['mean_weight'] == pytest.approx(1)


@pytest.mark.parametrize('kind', ['gap', 'duplicate', 'zero', 'nan'])
def test_invalid_prices_rejected(kind):
    p = prices(15)
    if kind == 'gap': p = p.drop(p.index[5])
    if kind == 'duplicate': p.index = list(p.index[:14])+[p.index[13]]
    if kind == 'zero': p.iloc[4,0] = 0
    if kind == 'nan': p.iloc[4,0] = np.nan
    with pytest.raises(ValueError): validate_prices(p)


def test_larger_cost_lowers_terminal_wealth_all_strategies():
    p = prices()
    a, b = run_all(p, fee=0), run_all(p, fee=.002)
    for k in a:
        assert b[k].equity.iloc[-1] <= a[k].equity.iloc[-1]+1e-10
        assert b[k].cash.min() > -1e-10
        assert b[k].weight.between(-1e-10, 1+1e-10).all()
