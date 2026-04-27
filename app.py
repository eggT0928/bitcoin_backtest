"""
Streamlit dashboard for BTC moving-average backtest variants.

실행:
streamlit run app.py
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


st.set_page_config(
    page_title="BTC 이동평균 전략 비교",
    page_icon="₿",
    layout="wide",
)


# =========================
# 전략 정의
# =========================

STRATEGIES = {
    "original": {
        "label": "원안 전략",
        "description": "5/25/99일선 상향 돌파로 분할매수, 5일선 하향 돌파 시 전량 매도",
        "sell_mode": "original",
        "confirm_days": 1,
        "buffer_pct": 0.0,
        "frequency": "daily",
    },
    "improved": {
        "label": "개선 매도 전략",
        "description": "매수는 원안 유지, 5일선 하락 50%, 25일선 하락 25%, 99일선 하락 0%",
        "sell_mode": "partial",
        "confirm_days": 1,
        "buffer_pct": 0.0,
        "frequency": "daily",
    },
    "confirm2": {
        "label": "개선+2일 확인",
        "description": "개선 매도 전략에 2일 연속 확인 규칙 추가",
        "sell_mode": "partial",
        "confirm_days": 2,
        "buffer_pct": 0.0,
        "frequency": "daily",
    },
    "buffer1": {
        "label": "개선+1% 완충",
        "description": "120일선 기준 ±1% 완충 구간을 두고 돌파 인정",
        "sell_mode": "partial",
        "confirm_days": 1,
        "buffer_pct": 0.01,
        "frequency": "daily",
    },
    "confirm2_buffer1": {
        "label": "개선+2일+1% 완충",
        "description": "2일 연속 확인과 ±1% 완충 구간을 함께 적용",
        "sell_mode": "partial",
        "confirm_days": 2,
        "buffer_pct": 0.01,
        "frequency": "daily",
    },
    "weekly": {
        "label": "개선+주 1회 판단",
        "description": "개선 매도 전략을 매주 일요일 종가 기준으로만 판단",
        "sell_mode": "partial",
        "confirm_days": 1,
        "buffer_pct": 0.0,
        "frequency": "weekly",
    },
}

BUYHOLD_LABEL = "BTC Buy & Hold"


# =========================
# 데이터 다운로드
# =========================

@st.cache_data(ttl=60 * 60)
def download_price_data(
    ticker: str,
    start: str,
    end: Optional[str] = None,
) -> pd.DataFrame:
    """
    yfinance에서 가격 데이터를 다운로드합니다.
    """
    import yfinance as yf

    df = yf.download(
        ticker,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
    )

    if df.empty:
        raise ValueError("가격 데이터를 불러오지 못했습니다.")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    out = df[["Close"]].copy()
    out.columns = ["close"]
    out.index = pd.to_datetime(out.index)
    out = out.dropna()

    return out


# =========================
# 이동평균 및 신호
# =========================

def add_moving_averages(df: pd.DataFrame) -> pd.DataFrame:
    """
    이동평균선을 계산합니다.
    """
    out = df.copy()

    for n in [5, 25, 99, 120]:
        out[f"ma{n}"] = out["close"].rolling(n).mean()

    return out


def state_signal(state: pd.Series, confirm_days: int) -> pd.Series:
    """
    조건이 confirm_days일 연속 성립한 첫날만 True로 만듭니다.
    confirm_days=1이면 일반적인 상태 전환 신호와 같습니다.
    """
    state = state.fillna(False).astype(bool)

    if confirm_days <= 1:
        confirmed = state
    else:
        confirmed = state.rolling(confirm_days).sum().eq(confirm_days).fillna(False)

    return confirmed & ~confirmed.shift(1).fillna(False)


def add_cross_signals(
    df: pd.DataFrame,
    confirm_days: int = 1,
    buffer_pct: float = 0.0,
) -> pd.DataFrame:
    """
    상향/하향 돌파 신호를 계산합니다.

    buffer_pct=0.01이면:
    - 상향 돌파 인정 기준: 단기선 > 120일선 * 1.01
    - 하향 돌파 인정 기준: 단기선 < 120일선 * 0.99
    - 그 사이 구간은 기존 비중 유지
    """
    out = df.copy()
    upper = out["ma120"] * (1.0 + buffer_pct)
    lower = out["ma120"] * (1.0 - buffer_pct)

    for n in [5, 25, 99]:
        up_state = out[f"ma{n}"] > upper
        down_state = out[f"ma{n}"] < lower

        out[f"up_state_{n}"] = up_state.fillna(False)
        out[f"down_state_{n}"] = down_state.fillna(False)
        out[f"cross_up_{n}"] = state_signal(up_state, confirm_days)
        out[f"cross_down_{n}"] = state_signal(down_state, confirm_days)

    return out


def initial_position_from_state(row: pd.Series, buffer_pct: float = 0.0) -> float:
    """
    백테스트 시작일에 이미 조건이 충족되어 있으면 현재 상태에 맞춰 초기 비중을 설정합니다.
    """
    if pd.isna(row["ma120"]):
        return 0.0

    upper = row["ma120"] * (1.0 + buffer_pct)
    position = 0.0

    if row["ma5"] > upper:
        position = 0.50
    if row["ma25"] > upper:
        position = 0.75
    if row["ma99"] > upper:
        position = 1.00

    return position


def calculate_event_position(
    signal_df: pd.DataFrame,
    sell_mode: str,
    buffer_pct: float,
) -> pd.Series:
    """
    일봉 또는 주봉 신호 데이터에서 전략 비중을 계산합니다.
    """
    positions = []
    position = 0.0
    initialized = False

    for _, row in signal_df.iterrows():
        if pd.isna(row["ma120"]):
            positions.append(0.0)
            continue

        if not initialized:
            position = initial_position_from_state(row, buffer_pct)
            initialized = True

        # 매도 신호를 먼저 반영합니다.
        if sell_mode == "original":
            if row["cross_down_5"]:
                position = 0.0
        elif sell_mode == "partial":
            if row["cross_down_99"]:
                position = 0.0
            elif row["cross_down_25"]:
                position = min(position, 0.25)
            elif row["cross_down_5"]:
                position = min(position, 0.50)
        else:
            raise ValueError(f"알 수 없는 sell_mode입니다: {sell_mode}")

        # 매수 신호를 반영합니다.
        if row["cross_up_5"]:
            position = max(position, 0.50)
        if row["cross_up_25"]:
            position = max(position, 0.75)
        if row["cross_up_99"]:
            position = max(position, 1.00)

        positions.append(position)

    return pd.Series(positions, index=signal_df.index)


def calculate_strategy_position(df: pd.DataFrame, config: dict) -> pd.Series:
    """
    전략 설정값에 따라 일별 투자 비중을 계산합니다.
    """
    frequency = config["frequency"]
    confirm_days = config["confirm_days"]
    buffer_pct = config["buffer_pct"]
    sell_mode = config["sell_mode"]

    if frequency == "daily":
        signal_df = add_cross_signals(df, confirm_days=confirm_days, buffer_pct=buffer_pct)
        position = calculate_event_position(signal_df, sell_mode=sell_mode, buffer_pct=buffer_pct)
        return position.reindex(df.index).fillna(0.0)

    if frequency == "weekly":
        # 비트코인은 매일 거래되므로 일요일 데이터를 주간 판단일로 사용합니다.
        # 주식형 티커처럼 일요일 데이터가 없는 경우를 대비해 W-SUN의 마지막 관측값을 사용합니다.
        weekly = df.resample("W-SUN").last().dropna(subset=["close"])
        weekly = add_cross_signals(weekly, confirm_days=confirm_days, buffer_pct=buffer_pct)
        weekly_position = calculate_event_position(weekly, sell_mode=sell_mode, buffer_pct=buffer_pct)

        # 주간 판단일에 결정된 비중을 다음 판단일까지 유지합니다.
        position = weekly_position.reindex(df.index, method="ffill").fillna(0.0)
        return position

    raise ValueError(f"알 수 없는 frequency입니다: {frequency}")


# =========================
# 백테스트
# =========================

def run_strategy_backtest(
    df: pd.DataFrame,
    position: pd.Series,
    fee_rate: float,
) -> pd.DataFrame:
    """
    전략 수익률과 누적 평가금을 계산합니다.

    룩어헤드 방지:
    오늘 종가 기준으로 신호를 확인했다고 보고,
    오늘 계산된 비중은 다음 날 수익률부터 반영합니다.
    """
    out = df.copy()
    out["position"] = position.reindex(out.index).fillna(0.0)
    out["btc_return"] = out["close"].pct_change().fillna(0.0)
    out["applied_position"] = out["position"].shift(1).fillna(0.0)
    out["turnover"] = out["position"].diff().abs().fillna(0.0)
    out["fee"] = out["turnover"] * fee_rate
    out["strategy_return"] = out["applied_position"] * out["btc_return"] - out["fee"]
    out["equity"] = (1.0 + out["strategy_return"]).cumprod()
    return out


def run_buy_and_hold_backtest(df: pd.DataFrame) -> pd.DataFrame:
    """
    비트코인 단순 보유 전략을 계산합니다.
    """
    out = df.copy()
    out["position"] = 1.0
    out["btc_return"] = out["close"].pct_change().fillna(0.0)
    out["strategy_return"] = out["btc_return"]
    out["equity"] = (1.0 + out["btc_return"]).cumprod()
    return out


# =========================
# 성과지표
# =========================

def calculate_recovery_stats(equity: pd.Series) -> dict:
    """
    전고점 회복 기간 관련 지표를 계산합니다.
    """
    equity = equity.dropna()
    peak = equity.cummax()
    underwater = equity < peak

    periods = []
    start_date = None

    for date, is_underwater in underwater.items():
        if is_underwater and start_date is None:
            start_date = date
        elif not is_underwater and start_date is not None:
            periods.append((date - start_date).days)
            start_date = None

    if start_date is not None:
        periods.append((equity.index[-1] - start_date).days)

    if not periods:
        return {
            "최장회복기간_일": 0,
            "평균회복기간_일": 0.0,
        }

    return {
        "최장회복기간_일": max(periods),
        "평균회복기간_일": float(np.mean(periods)),
    }


def calculate_metrics(
    equity: pd.Series,
    returns: pd.Series,
    position: Optional[pd.Series] = None,
) -> dict:
    """
    CAGR, MDD, 변동성, 샤프, 소르티노, UPI 등을 계산합니다.
    """
    equity = equity.dropna()
    returns = returns.reindex(equity.index).fillna(0.0)

    total_days = (equity.index[-1] - equity.index[0]).days
    years = total_days / 365.25

    final_value = equity.iloc[-1]
    cagr = final_value ** (1 / years) - 1 if years > 0 else np.nan

    drawdown = equity / equity.cummax() - 1
    mdd = drawdown.min()
    volatility = returns.std() * np.sqrt(365.25)

    sharpe = np.nan
    if returns.std() != 0:
        sharpe = returns.mean() / returns.std() * np.sqrt(365.25)

    downside_returns = returns[returns < 0]
    sortino = np.nan
    if downside_returns.std() != 0:
        sortino = returns.mean() / downside_returns.std() * np.sqrt(365.25)

    ulcer_index = np.sqrt(np.mean(np.square(drawdown[drawdown < 0])))
    upi = np.nan
    if ulcer_index != 0:
        upi = cagr / ulcer_index

    avg_position = np.nan
    trade_count = np.nan
    turnover_per_year = np.nan

    if position is not None:
        position = position.reindex(equity.index).fillna(0.0)
        position_change = position.diff().fillna(0.0)
        avg_position = position.mean()
        trade_count = int((position_change.abs() > 0).sum())
        turnover_per_year = position_change.abs().sum() / years if years > 0 else np.nan

    recovery_stats = calculate_recovery_stats(equity)

    return {
        "최종배율": final_value,
        "CAGR": cagr,
        "MDD": mdd,
        "연변동성": volatility,
        "Sharpe": sharpe,
        "Sortino": sortino,
        "UPI": upi,
        "평균투자비중": avg_position,
        "거래횟수": trade_count,
        "연평균회전율": turnover_per_year,
        **recovery_stats,
    }


def format_percent(x: float) -> str:
    if pd.isna(x):
        return ""
    return f"{x:.2%}"


def format_number(x: float) -> str:
    if pd.isna(x):
        return ""
    return f"{x:,.2f}"


def make_display_metrics(metrics_df: pd.DataFrame) -> pd.DataFrame:
    """
    화면 표시용 성과표를 만듭니다.
    """
    display = metrics_df.copy()

    for col in ["CAGR", "MDD", "연변동성", "평균투자비중", "연평균회전율"]:
        display[col] = display[col].map(format_percent)

    for col in ["최종배율", "Sharpe", "Sortino", "UPI", "거래횟수", "최장회복기간_일", "평균회복기간_일"]:
        display[col] = display[col].map(format_number)

    return display


# =========================
# 그래프
# =========================

def make_equity_chart(equity_panel: pd.DataFrame, selected_labels: list[str]) -> go.Figure:
    """
    누적 수익률 그래프를 만듭니다.
    """
    fig = go.Figure()

    for label in selected_labels:
        fig.add_trace(
            go.Scatter(
                x=equity_panel.index,
                y=equity_panel[label],
                mode="lines",
                name=label,
            )
        )

    fig.update_layout(
        title="누적 수익률 비교, 시작점 1",
        xaxis_title="날짜",
        yaxis_title="평가배율, 로그 스케일",
        yaxis_type="log",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=600,
    )

    return fig


def make_drawdown_chart(equity_panel: pd.DataFrame, selected_labels: list[str]) -> go.Figure:
    """
    낙폭 그래프를 만듭니다.
    """
    fig = go.Figure()

    for label in selected_labels:
        equity = equity_panel[label]
        drawdown = equity / equity.cummax() - 1
        fig.add_trace(
            go.Scatter(
                x=equity_panel.index,
                y=drawdown,
                mode="lines",
                name=label,
            )
        )

    fig.update_layout(
        title="MDD / Drawdown 비교",
        xaxis_title="날짜",
        yaxis_title="Drawdown",
        yaxis_tickformat=".0%",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=430,
    )

    return fig


def make_position_chart(position_panel: pd.DataFrame, selected_labels: list[str]) -> go.Figure:
    """
    투자 비중 그래프를 만듭니다.
    """
    fig = go.Figure()

    for label in selected_labels:
        if label == BUYHOLD_LABEL:
            continue
        fig.add_trace(
            go.Scatter(
                x=position_panel.index,
                y=position_panel[label],
                mode="lines",
                name=label,
            )
        )

    fig.update_layout(
        title="전략별 투자 비중",
        xaxis_title="날짜",
        yaxis_title="투자 비중",
        yaxis_tickformat=".0%",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=380,
    )

    return fig


# =========================
# 앱 본문
# =========================

st.title("₿ BTC 이동평균 전략 비교 대시보드")

st.markdown(
    """
    원안 전략, 개선 매도 전략, 휩쏘 완화 전략들, 그리고 매수 후 보유를 한 번에 비교합니다.

    **체리피킹을 줄이기 위해 단순한 후보만 비교합니다.**
    2일 확인, 1% 완충, 2일+1% 완충, 주 1회 판단처럼 사전에 정한 규칙만 비교합니다.
    """
)

with st.expander("전략 규칙 보기", expanded=False):
    strategy_info = pd.DataFrame(
        [
            {
                "전략": cfg["label"],
                "설명": cfg["description"],
                "확인일수": cfg["confirm_days"],
                "완충구간": f"{cfg['buffer_pct']:.1%}",
                "판단주기": "매일" if cfg["frequency"] == "daily" else "주 1회",
            }
            for cfg in STRATEGIES.values()
        ]
    )
    st.dataframe(strategy_info, use_container_width=True)

with st.sidebar:
    st.header("백테스트 설정")

    ticker = st.text_input("티커", value="BTC-USD")
    start_date = st.date_input("시작일", value=pd.Timestamp("2014-09-17").date())
    fee_rate = st.number_input(
        "거래비용, 비중 100% 변화 기준",
        min_value=0.0,
        max_value=0.05,
        value=0.001,
        step=0.0005,
        format="%.4f",
    )
    trim_to_signal = st.checkbox("120일선 계산 이후부터 비교", value=True)

    st.divider()
    st.caption("그래프에 표시할 전략")
    default_graph_labels = [
        "원안 전략",
        "개선 매도 전략",
        "개선+2일 확인",
        "개선+1% 완충",
        "개선+주 1회 판단",
        BUYHOLD_LABEL,
    ]
    selected_labels = st.multiselect(
        "표시 전략 선택",
        options=[cfg["label"] for cfg in STRATEGIES.values()] + [BUYHOLD_LABEL],
        default=default_graph_labels,
    )

    st.caption("예: 0.001 = 0.1%")

try:
    raw = download_price_data(ticker=ticker, start=str(start_date))
    df = add_moving_averages(raw)

    if trim_to_signal:
        df = df.dropna(subset=["ma120"]).copy()

    if df.empty:
        st.error("120일 이동평균 계산 이후 사용할 수 있는 데이터가 없습니다.")
        st.stop()

    backtests = {}
    metrics = {}
    position_panel = pd.DataFrame(index=df.index)
    equity_panel = pd.DataFrame(index=df.index)
    return_panel = pd.DataFrame(index=df.index)

    for _, config in STRATEGIES.items():
        label = config["label"]
        position = calculate_strategy_position(df, config)
        bt = run_strategy_backtest(df, position, fee_rate)

        backtests[label] = bt
        position_panel[label] = bt["position"]
        equity_panel[label] = bt["equity"]
        return_panel[label] = bt["strategy_return"]
        metrics[label] = calculate_metrics(bt["equity"], bt["strategy_return"], bt["position"])

    buyhold_bt = run_buy_and_hold_backtest(df)
    backtests[BUYHOLD_LABEL] = buyhold_bt
    position_panel[BUYHOLD_LABEL] = 1.0
    equity_panel[BUYHOLD_LABEL] = buyhold_bt["equity"]
    return_panel[BUYHOLD_LABEL] = buyhold_bt["strategy_return"]
    metrics[BUYHOLD_LABEL] = calculate_metrics(
        buyhold_bt["equity"],
        buyhold_bt["strategy_return"],
        buyhold_bt["position"],
    )

    metrics_df = pd.DataFrame(metrics).T
    display_metrics = make_display_metrics(metrics_df)

    latest = df.iloc[-1]
    latest_positions = position_panel.iloc[-1]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("기준일", str(df.index[-1].date()))
    col2.metric("BTC 종가", f"{latest['close']:,.2f}")
    col3.metric("5일선 / 120일선", f"{latest['ma5']:,.0f} / {latest['ma120']:,.0f}")
    col4.metric("거래비용", f"{fee_rate:.2%}")

    st.subheader("현재 전략별 투자 비중")
    current_position_df = pd.DataFrame(
        {
            "현재 비중": latest_positions,
        }
    )
    current_position_df["현재 비중"] = current_position_df["현재 비중"].map(format_percent)
    st.dataframe(current_position_df, use_container_width=True)

    st.subheader("성과 요약표")
    st.dataframe(display_metrics, use_container_width=True)

    st.subheader("누적 수익률 그래프")
    st.plotly_chart(make_equity_chart(equity_panel, selected_labels), use_container_width=True)

    st.subheader("낙폭 그래프")
    st.plotly_chart(make_drawdown_chart(equity_panel, selected_labels), use_container_width=True)

    st.subheader("투자 비중 변화")
    st.plotly_chart(make_position_chart(position_panel, selected_labels), use_container_width=True)

    st.subheader("최근 일별 데이터")
    daily_panel = pd.concat(
        [
            df[["close", "ma5", "ma25", "ma99", "ma120"]],
            position_panel.add_suffix("_position"),
            equity_panel.add_suffix("_equity"),
            return_panel.add_suffix("_return"),
        ],
        axis=1,
    )
    st.dataframe(daily_panel.tail(500), use_container_width=True)

    csv_metrics = metrics_df.to_csv(encoding="utf-8-sig")
    csv_daily = daily_panel.to_csv(encoding="utf-8-sig")

    dl1, dl2 = st.columns(2)
    dl1.download_button(
        "성과표 CSV 다운로드",
        data=csv_metrics,
        file_name="btc_strategy_compare_metrics.csv",
        mime="text/csv",
    )
    dl2.download_button(
        "일별 백테스트 데이터 CSV 다운로드",
        data=csv_daily,
        file_name="btc_strategy_compare_daily.csv",
        mime="text/csv",
    )

except Exception as exc:
    st.error(f"실행 중 오류가 발생했습니다: {exc}")
