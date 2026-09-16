"""Run only preregistered comparisons. No search, objective, or parameter selection."""
from __future__ import annotations
import argparse
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import pandas as pd
import numpy as np
from backtest_engine import *

OUT = ROOT / 'research/results'


def export(frame, name):
    frame.to_csv(OUT / name, encoding='utf-8-sig', float_format='%.10g')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', action='store_true', help='Explicitly replace the frozen snapshot')
    parser.add_argument('--provider', choices=['coinmetrics','yahoo'], default='coinmetrics')
    args = parser.parse_args()
    if args.download:
        save_snapshot(download_prices(args.provider))
    p = load_snapshot()
    OUT.mkdir(parents=True, exist_ok=True)
    signals = make_signals(p)
    paths = run_all(p, signals)
    export(metric_table(paths), 'full_metrics.csv')
    export(period_table(paths), 'period_metrics.csv')
    export(annual_returns(paths), 'annual_returns.csv')
    export(pd.concat(paths, names=['strategy', 'date']), 'daily_paths.csv')
    # Temporal holdout without yearly model selection; all folds keep parameters fixed.
    folds, cold = [], []
    start = next(iter(paths.values())).index[0]
    for year in range(2019, p.index[-1].year+1):
        train = metric_table({k:slice_path(v, None, f'{year-1}-12-31') for k,v in paths.items()})
        test = metric_table({k:slice_path(v, f'{year}-01-01', f'{year}-12-31') for k,v in paths.items()})
        for role, frame in [('expanding_past', train), ('next_year_holdout', test)]:
            frame['fold_year'], frame['role'] = year, role
            folds.append(frame.reset_index())
    export(pd.concat(folds, ignore_index=True), 'chronological_folds.csv')
    for period, (a,b) in PERIODS.items():
        if pd.Timestamp(a) > p.index[-1]: continue
        table = metric_table(run_all(p, signals, start=a, end=b))
        table['period'] = period
        cold.append(table.reset_index())
    export(pd.concat(cold, ignore_index=True), 'cold_start_periods.csv')
    costs = []
    for fee in [0., .001, .002]:
        fee_paths = run_all(p, signals, fee=fee)
        table = period_table(fee_paths)
        table['one_way_cost'] = fee
        costs.append(table)
    export(pd.concat(costs, ignore_index=True), 'cost_sensitivity.csv')

    robustness = []
    def check(family, value, spec, keys, common_start='2015-08-02', delay=1):
        variant = make_signals(p, **spec)
        run = run_all(p, variant, start=common_start, delay=delay)
        # Common start includes max delay, max month/vol window for the whole family.
        table = period_table({k:run[k] for k in keys})
        table['family'], table['value'] = family, str(value)
        table['effective_start'] = str(next(iter(run.values())).index[0].date())
        robustness.append(table)
    event_keys = ['original','improved','confirm2','buffer1','confirm2_buffer1','weekly']
    for ma in [100,120,150]:
        check('base_ma', ma, {'base_ma':ma}, event_keys+['weekly_price','weekly_price_vol'])
    for months in [8,10,12]:
        check('monthly_window', months, {'monthly_window':months}, ['monthly_10m'], '2015-10-02')
    for target in [.3,.4,.5]:
        check('vol_target', target, {'vol_target':target}, ['weekly_price_vol'])
    for window in [30,60,90]:
        check('vol_window', window, {'vol_window':window}, ['weekly_price_vol'])
    for weekday in [4,6,1]:
        check('weekday', weekday, {'weekday':weekday}, ['weekly','weekly_price','weekly_price_vol'])
    for delay in [1,2]:
        check('execution_delay', delay, {}, list(LABELS), '2015-08-03', delay)
    export(pd.concat(robustness, ignore_index=True), 'robustness.csv')

    static = pd.Series(.5, index=p.index)
    static_path = simulate(p, static, static.diff().abs().gt(0), start=start)
    export(period_table({'static_initial_50pct':static_path}), 'static_risk_control.csv')
    export(pd.DataFrame({k:{'signal_target':v.signal_target.iloc[-1], 'executed_target':v.executed_target.iloc[-1],
                             'actual_weight':v.weight.iloc[-1], 'as_of':str(v.index[-1].date())} for k,v in paths.items()}).T,
           'current_weights.csv')
    manifest = dict(run_at_utc=pd.Timestamp.now(tz='UTC').isoformat(), python=platform.python_version(),
                    pandas=pd.__version__, numpy=np.__version__, prereg_commit='cea80794a06460e581af2316ef85fa43c35e7613',
                    code_commit=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
                    data_sha256=hashlib.sha256(DATA_PATH.read_bytes()).hexdigest(),
                    prereg_sha256=hashlib.sha256((ROOT/'research/PREREGISTRATION.md').read_bytes()).hexdigest(),
                    sources_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                                    for name in ['backtest_engine.py','legacy_signals.py','run_research.py']},
                    start=str(start.date()), end=str(p.index[-1].date()), fee=.001, delay=1,
                    candidate_changes_after_results=False)
    (OUT/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'start':manifest['start'],'end':manifest['end'],'rows':len(p),'strategies':len(paths)}))
    print(metric_table(paths)[['CAGR','MDD','Sharpe','Sortino','UPI','turnover_pa']].round(4).to_string())


if __name__ == '__main__':
    main()
