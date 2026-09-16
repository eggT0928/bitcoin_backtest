"""BTC research dashboard. Run: streamlit run app.py"""
from __future__ import annotations
import json
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from backtest_engine import (ROOT, DATA_PATH, LABELS, PERIODS, load_snapshot,
                             download_prices, make_signals, run_all, slice_path, metric_table,
                             period_table, annual_returns, drawdown)
from legacy_signals import STRATEGIES

st.set_page_config(page_title='BTC 추세추종 연구실', page_icon='₿', layout='wide')
METRIC_NAMES = {'CAGR':'CAGR', 'MDD':'MDD', 'volatility':'연변동성', 'Sharpe':'Sharpe', 'Sortino':'Sortino',
                'Ulcer':'Ulcer Index', 'UPI':'UPI', 'Calmar':'Calmar', 'mean_weight':'평균 투자비중',
                'mean_cash':'평균 현금비중', 'orders':'편도 주문수', 'turnover_pa':'연 turnover (배)',
                'recovery_max_days':'완료 회복 최장(일)', 'recovery_mean_days':'완료 회복 평균(일)',
                'unrecovered_days':'미회복 경과(일)', 'underwater_max_days':'최장 수중기간(일)',
                'recovered_episodes':'회복 완료 건수', 'fee_sum':'비용/NAV 합계', 'final_multiple':'최종배율',
                'reversal_14d_count':'14일내 방향반전 수', 'reversal_14d_rate':'14일내 방향반전 비율'}
PCT = ['CAGR','MDD','volatility','Ulcer','mean_weight','mean_cash','fee_sum','reversal_14d_rate']


@st.cache_data(show_spinner=False)
def snapshot():
    return load_snapshot()


@st.cache_data(ttl=3600, show_spinner=False)
def fresh_data(provider):
    return download_prices(provider)


@st.cache_data(show_spinner=False)
def calculate(prices, fee, delay):
    return run_all(prices, make_signals(prices), fee=fee, delay=delay)


def display_metrics(frame):
    display = frame.copy()
    if 'strategy' in display.columns:
        display['strategy'] = display.strategy.map(LABELS).fillna(display.strategy)
        display = display.rename(columns={'strategy':'전략', 'period':'기간'})
    else:
        display.index = [LABELS.get(k,k) for k in display.index]
        display.index.name = '전략'
    fmt = {METRIC_NAMES[k]:'{:.2%}' if k in PCT else '{:,.2f}' for k in display.columns if k in METRIC_NAMES}
    return display.rename(columns=METRIC_NAMES).style.format(fmt, na_rep='—')


def line_chart(paths, field, title, log=False):
    fig = go.Figure()
    for key,path in paths.items():
        series = drawdown(path) if field == 'drawdown' else path[field]
        if field in ('equity','drawdown'):
            series = pd.concat([pd.Series([1. if field=='equity' else 0.],
                                index=[series.index[0]-pd.Timedelta(days=1)]), series])
        fig.add_trace(go.Scatter(x=series.index, y=series, name=LABELS[key], mode='lines', line={'width':1.6}))
    fig.update_layout(title=title, height=470, hovermode='x unified',
                      yaxis_type='log' if log else 'linear', legend={'orientation':'h','y':-0.22},
                      margin={'t':55,'b':90}, template='plotly_white')
    if field in ('drawdown','weight'): fig.update_yaxes(tickformat='.0%')
    return fig


st.title('₿ BTC 추세추종 연구실')
st.caption('5 / 20 / 65 / 120 · 사전 고정한 후보 · 같은 가격, 비용, 실행 시점으로 비교')
with st.sidebar:
    st.header('분석 조건')
    source = st.selectbox('데이터', ['연구 고정 스냅샷', 'Coin Metrics 새로 조회', 'Yahoo Finance 새로 조회'])
    fee_pct = st.number_input('편도 거래비용 (%)', min_value=0., max_value=2., value=.1, step=.05, format='%.2f')
    delay = st.selectbox('종가 신호 후 체결 지연', [1,2], format_func=lambda n:f'{n}일 뒤 종가 체결')
    st.caption('기본: t 종가 신호 → t+1 종가 체결 → t+2 수익부터 새 보유량 반영')

try:
    if source == '연구 고정 스냅샷':
        prices = snapshot()
        metadata = json.loads(DATA_PATH.with_suffix('.json').read_text(encoding='utf-8'))
        provider_name = metadata['provider']
    else:
        provider = 'coinmetrics' if source.startswith('Coin') else 'yahoo'
        prices = fresh_data(provider)
        provider_name = prices.attrs.get('provider', source)
    with st.spinner('동일한 실행 조건으로 계산 중…'):
        all_paths = calculate(prices, fee_pct/100, delay)
except Exception as exc:
    st.error(f'데이터를 계산하지 못했습니다: {exc}')
    st.info('네트워크 제한이 있는 경우 데이터에서 연구 고정 스냅샷을 선택하세요.')
    st.stop()

first = next(iter(all_paths.values())).index[0]
last = prices.index[-1]
st.caption(f'출처: {provider_name} · 가격 {prices.index[0]:%Y-%m-%d}~{last:%Y-%m-%d} · 성과 공통 시작 {first:%Y-%m-%d} · UTC 일말')
age = (pd.Timestamp.now(tz='UTC').tz_localize(None).normalize()-last).days
if age > 3:
    st.warning(f'자료 마지막 날짜는 {last:%Y-%m-%d}입니다({age}일 전). 아래 최신 비중은 이 자료 기준이며 실시간 비중이 아닙니다.')
with st.sidebar:
    period = st.selectbox('평가 기간', list(PERIODS)+['직접 선택'])
    if period == '직접 선택':
        start_date = st.date_input('시작일', first.date(), min_value=first.date(), max_value=last.date())
        end_date = st.date_input('종료일', last.date(), min_value=first.date(), max_value=last.date())
        start, end = str(start_date), str(end_date)
    else:
        start, end = PERIODS[period]
    mode = st.radio('하위기간 계산', ['전체 경로 승계', '시작일 신규 투자'])
    selected = st.multiselect('표·그래프 전략', list(LABELS), default=list(LABELS), format_func=LABELS.get)
if not selected:
    st.info('한 개 이상의 전략을 선택하세요.')
    st.stop()
if pd.Timestamp(start) > pd.Timestamp(end or last):
    st.error('시작일은 종료일보다 빨라야 합니다.')
    st.stop()
if mode == '시작일 신규 투자':
    paths = run_all(prices, fee=fee_pct/100, delay=delay, start=start, end=end)
else:
    paths = {k:slice_path(v,start,end) for k,v in all_paths.items()}
paths = {k:paths[k] for k in selected if not paths[k].empty}
if not paths:
    st.info('선택 기간에 성과 데이터가 없습니다.')
    st.stop()
table = metric_table(paths)
sample = next(iter(paths.values()))
st.write(f'**선택 성과 구간: {sample.index[0]:%Y-%m-%d} ~ {sample.index[-1]:%Y-%m-%d}** · 편도 {fee_pct:.2f}% · {mode}')
st.caption('현금 이자·무위험수익률 0%, USD 기준, 공매도·레버리지 없음. 거래 사이 실제 투자비중은 가격에 따라 변합니다.')
tabs = st.tabs(['성과와 그래프','기간별 비교','비용·안정성','자료 기준 비중','연구 근거'])
with tabs[0]:
    st.subheader('성과표')
    st.dataframe(display_metrics(table), width='stretch')
    st.caption('평균 비중은 각 일간 수익에 적용된 실제 비중. 거래수는 편도 주문수이며, turnover는 실제 거래대금/NAV의 연간 합입니다.')
    st.caption('완료 회복기간은 이전 고점~회복일. 미회복 경과와 최장 수중기간을 별도로 봐야 하며, —는 회복 완료 사례 없음입니다.')
    st.plotly_chart(line_chart(paths,'equity','누적 평가배율 · 로그 눈금',True), width='stretch')
    st.plotly_chart(line_chart(paths,'drawdown','Drawdown · 직전 고점 대비'), width='stretch')
    st.plotly_chart(line_chart(paths,'weight','실제 BTC 투자비중'), width='stretch')
    st.subheader('연도별 수익률')
    annual = annual_returns(paths).rename(columns=LABELS)
    st.dataframe(annual.style.format('{:.2%}',na_rep='—'), width='stretch')
    st.caption('첫해와 마지막 해는 선택한 날짜까지만 포함한 부분 연도일 수 있습니다.')
    st.subheader('거래 부담')
    st.dataframe(display_metrics(table[['orders','turnover_pa','reversal_14d_count','reversal_14d_rate']]), width='stretch')
    st.caption('14일 내 매수↔매도 반전은 휩쏘 대리 지표입니다. 손실 왕복 거래 수가 아니며 변동성 리밸런싱도 포함합니다. 최초 진입은 반전 집계에서 제외됩니다.')
    st.download_button('선택 성과표 CSV', table.rename(index=LABELS).to_csv().encode('utf-8-sig'), 'btc_metrics.csv','text/csv')
    st.download_button('선택 일별 결과 CSV', pd.concat(paths,names=['strategy','date']).to_csv().encode('utf-8-sig'), 'btc_daily.csv','text/csv')
    st.download_button('연도별 수익률 CSV', annual.to_csv().encode('utf-8-sig'), 'btc_annual.csv','text/csv')
with tabs[1]:
    st.subheader('고정 시장국면 비교')
    st.caption('이 표는 상단 기간 선택과 무관하게 모든 고정 구간을 비교하며 전체 경로를 승계합니다. 비용·체결 지연·선택 전략은 동일합니다.')
    pt = period_table({k:all_paths[k] for k in selected})
    period_metric = st.selectbox('비교 지표', ['CAGR','MDD','Sharpe','Sortino','UPI','Calmar','turnover_pa','underwater_max_days'], format_func=lambda k:METRIC_NAMES[k])
    pivot = pt.pivot(index='period',columns='strategy',values=period_metric).rename(columns=LABELS)
    st.dataframe(pivot.style.format('{:.2%}' if period_metric in PCT else '{:,.2f}'), width='stretch')
    with st.expander('기간별 전체 지표'): st.dataframe(display_metrics(pt), width='stretch')
    st.download_button('기간별 지표 CSV', pt.to_csv(index=False).encode('utf-8-sig'),'btc_periods.csv','text/csv')
with tabs[2]:
    st.subheader('같은 구간의 거래비용 민감도')
    cost_frames = []
    for fee in [0.,.001,.002]:
        runs = calculate(prices,fee,delay)
        if mode == '시작일 신규 투자': runs = run_all(prices,fee=fee,delay=delay,start=start,end=end)
        else: runs = {k:slice_path(v,start,end) for k,v in runs.items()}
        mt = metric_table({k:runs[k] for k in selected if not runs[k].empty}).reset_index()
        mt.insert(1,'편도 비용',f'{fee:.1%}')
        cost_frames.append(mt)
    ct = pd.concat(cost_frames,ignore_index=True)
    st.dataframe(display_metrics(ct[['strategy','편도 비용','CAGR','Sharpe','MDD','turnover_pa']]), width='stretch')
    st.subheader('사전 고정한 파라미터 주변값 검증')
    st.caption('아래는 보고서의 고정 스냅샷·편도 0.1% 연구 결과입니다. 상단 설정에 따라 바뀌지 않습니다. 가장 좋은 값을 고르는 도구가 아닙니다.')
    robust_path = ROOT/'research/results/robustness.csv'
    if robust_path.exists():
        robust = pd.read_csv(robust_path,index_col=0)
        family = st.selectbox('검증 항목', robust.family.unique().tolist())
        robust_period = st.selectbox('검증 구간',robust.period.unique().tolist())
        view = robust[(robust.family==family)&(robust.period==robust_period)&robust.strategy.isin(selected)]
        st.dataframe(display_metrics(view[['strategy','value','effective_start','CAGR','MDD','Sharpe','UPI','turnover_pa','underwater_max_days']]),width='stretch')
    st.info('시간순 검증은 2019년 이후 고정 규칙을 연별로 평가한 사후적 holdout입니다. 2026년에 이미 알려진 역사를 사용했으므로 진정한 미관측 OOS라고 주장하지 않습니다.')
with tabs[3]:
    st.subheader(f'자료 마지막 날 비중 · {last:%Y-%m-%d} UTC')
    st.caption('기간 선택과 무관한 마지막 데이터 기준입니다. 실제 계좌 주문이나 실시간 추천이 아닙니다.')
    current = pd.DataFrame({k:{'마지막 신호 목표':v.signal_target.iloc[-1], '마지막 체결 지시 목표':v.executed_target.iloc[-1],
                               '실제 모의 보유비중':v.weight.iloc[-1]} for k,v in all_paths.items() if k in selected}).T.rename(index=LABELS)
    st.dataframe(current.style.format('{:.1%}'), width='stretch')
    st.caption('신호 목표는 마지막 확정 종가로 계산된 목표, 체결 지시 목표는 지연 적용된 목표입니다. 실제 비중은 거래 이후 가격 움직임에 따라 달라집니다.')
with tabs[4]:
    st.subheader('보존한 기존 전략과 사전 고정한 연구 후보')
    for config in STRATEGIES.values(): st.markdown(f'**{config["label"]}** — {config["description"]}')
    st.markdown('**연구: 주간 가격·120일선** — 일요일 종가가 SMA120 위면 100%, 아래면 현금.\n\n'
                '**연구: 월말 10개월선** — 완결 월말 종가가 10개 월말 종가 평균 위면 100%, 아래면 현금.\n\n'
                '**연구: 주간 가격·변동성40%** — 주간 가격 신호가 상승이면 min(100%, 40% / 최근 60일 연변동성), 아니면 현금.')
    st.warning('연구 후보를 대시보드에 포함했다고 채택을 권하는 것은 아닙니다. 10개월선은 주변 기간에 민감하고, 변동성 조절은 최근 구간 부진과 많은 리밸런싱을 동반했습니다.')
    for filename,title in [('REPORT.md','최종 연구 보고서'),('LITERATURE.md','문헌 표'),('PREREGISTRATION.md','성과 계산 전 사전등록'),('AMENDMENTS.md','자료·구현 변경 이력')]:
        file = ROOT/'research'/filename
        if file.exists():
            content = file.read_text(encoding='utf-8')
            with st.expander(title): st.markdown(content)
            st.download_button(f'{title} 다운로드',content.encode('utf-8'),filename,'text/markdown',key=filename)
