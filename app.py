"""
Streamlit dashboard for BTC moving-average partial-sell backtest.

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
    page_title="BTC 이동평균 백테스트",
    page_icon="₿",
    layout="wide",
)


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
# 신호 계산
# =========================

def add_moving_averages(df: pd.DataFrame) -> pd.DataFrame:
    """
    이동평균선과 상향/하향 돌파 신호를 계산합니다.
    """
    out = df.copy()

    for n in [5, 25, 99, 120]:
        out[f"ma{n}"] = out["close"].rolling(n).mean()

    out["cross_up_5"] = (out["ma5"] > out["ma120"]) & (
        out["ma5"].shift(1) <= out["ma120"].shift(1)
    )
    out["cross_up_25"] = (out["ma25"] > out["ma120"]) & (
        out["ma25"].shift(1) <= out["ma120"].shift(1)
    )
    out["cross_up_99"] = (out["ma99"] > out["ma120"]) & (
        out["ma99"].shift(1) <= out["ma120"].shift(1)
    )

    out["cross_down_5"] = (out["ma5"] < out["ma120"]) & (
        out["ma5"].shift(1) >= out["ma120"].shift(1)
    )
    out["cross_down_25"] = (out["ma25"] < out["ma120"]) & (
        out["ma25"].shift(1) >= out["ma120"].shift(1)
    )
    out["cross_down_99"] = (out["ma99"] < out["ma120"]) & (
        out["ma99"].shift(1) >= out["ma120"].shift(1)
    )

    return out


def initial_position_from_current_ma(row: pd.Series) -> float:
    """
    백테스트 시작일에 이미 이동평균 조건이 충족되어 있는 경우
    현재 상태에 맞춰 초기 비중을 설정합니다.
    """
    position = 0.0

    if row["ma5"] > row["ma120"]:
        position = 0.50
    if row["ma25"] > row["ma120"]:
        position = 0.75
    if row["ma99"] > row["ma120"]:
        position = 1.00

    return position


def calculate_original_position(df: pd.DataFrame) -> pd.Series:
    """
    원안 전략 비중을 계산합니다.

    매수:
    - 5일선 상향 돌파: 50%
    - 25일선 상향 돌파: 75%
    - 99일선 상향 돌파: 100%

    매도:
    - 5일선 하향 돌파: 전량 매도
    """
    positions = []
    position = 0.0
    initialized = False

    for _, row in df.iterrows():
        if pd.isna(row["ma120"]):
            positions.append(0.0)
            continue

        if not initialized:
            position = initial_position_from_current_ma(row)
            initialized = True

        if row["cross_down_5"]:
            position = 0.0

        if row["cross_up_5"]:
            position = max(position, 0.50)
        if row["cross_up_25"]:
            position = max(position, 0.75)
        if row["cross_up_99"]:
            position = max(position, 1.00)

        positions.append(position)

    return pd.Series(positions, index=df.index, name="original_position")


def calculate_improved_position(df: pd.DataFrame) -> pd.Series:
    """
    개선 매도 전략 비중을 계산합니다.

    매수는 원안 유지:
    - 5일선 상향 돌파: 50%
    - 25일선 상향 돌파: 75%
    - 99일선 상향 돌파: 100%

    매도만 개선:
    - 5일선 하향 돌파: 50%로 축소
    - 25일선 하향 돌파: 25%로 축소
    - 99일선 하향 돌파: 전량 매도
    """
    positions = []
    position = 0.0
    initialized = False

    for _, row in df.iterrows():
        if pd.isna(row["ma120"]):
            positions.append(0.0)
            continue

        if not initialized:
            position = initial_position_from_current_ma(row)
            initialized = True

        if row["cross_down_99"]:
            position = 0.0
        elif row["cross_down_25"]:
            position = min(position, 0.25)
        elif row["cross_down_5"]:
            position = min(position, 0.50)

        if row["cross_up_5"]:
            position = max(position, 0.50)
        if row["cross_up_25"]:
            position = max(position, 0.75)
        if row["cross_up_99"]:
            position = max(position, 1.00)

        positions.append(position)

    return pd.Series(positions, index=df.index, name="improved_position")


# =========================
# 백테스트
# =========================

def run_strategy_backtest(
    df: pd.DataFrame,
    position_col: str,
    fee_rate: float,
) -> pd.DataFrame:
    """
    전략 수익률과 누적 평가금을 계산합니다.

    룩어헤드 방지:
    오늘 종가 기준으로 신호를 확인했다고 보고,
    오늘 계산된 비중은 다음 날 수익률부터 반영합니다.
    """
    out = df.copy()

    out["btc_return"] = out["close"].pct_change().fillna(0.0)
    out["applied_position"] = out[position_col].shift(1).fillna(0.0)

    out["turnover"] = out[position_col].diff().abs().fillna(0.0)
    out["fee"] = out["turnover"] * fee_rate

    out["strategy_return"] = out["applied_position"] * out["btc_return"] - out["fee"]
    out["equity"] = (1.0 + out["strategy_return"]).cumprod()

    return out


def run_buy_and_hold_backtest(df: pd.DataFrame) -> pd.DataFrame:
    """
    비트코인 단순 보유 전략을 계산합니다.
    """
    out = df.copy()
    out["btc_return"] = out["close"].pct_change().fillna(0.0)
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
    성과지표를 계산합니다.
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

def make_equity_chart(panel: pd.DataFrame) -> go.Figure:
    """
    누적 수익률 그래프를 만듭니다.
    """
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=panel.index,
            y=panel["original_equity"],
            mode="lines",
            name="원안 전략",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=panel.index,
            y=panel["improved_equity"],
            mode="lines",
            name="개선 매도 전략",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=panel.index,
            y=panel["buyhold_equity"],
            mode="lines",
            name="BTC Buy & Hold",
        )
    )

    fig.update_layout(
        title="누적 수익률 비교, 시작점 1",
        xaxis_title="날짜",
        yaxis_title="평가배율, 로그 스케일",
        yaxis_type="log",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=560,
    )

    return fig


def make_drawdown_chart(panel: pd.DataFrame) -> go.Figure:
    """
    낙폭 그래프를 만듭니다.
    """
    fig = go.Figure()

    series_map = {
        "원안 전략": panel["original_equity"],
        "개선 매도 전략": panel["improved_equity"],
        "BTC Buy & Hold": panel["buyhold_equity"],
    }

    for name, equity in series_map.items():
        drawdown = equity / equity.cummax() - 1
        fig.add_trace(
            go.Scatter(
                x=panel.index,
                y=drawdown,
                mode="lines",
                name=name,
            )
        )

    fig.update_layout(
        title="MDD / Drawdown 비교",
        xaxis_title="날짜",
        yaxis_title="Drawdown",
        yaxis_tickformat=".0%",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=420,
    )

    return fig


def make_position_chart(panel: pd.DataFrame) -> go.Figure:
    """
    투자 비중 그래프를 만듭니다.
    """
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=panel.index,
            y=panel["original_position"],
            mode="lines",
            name="원안 전략 비중",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=panel.index,
            y=panel["improved_position"],
            mode="lines",
            name="개선 매도 전략 비중",
        )
    )

    fig.update_layout(
        title="전략별 투자 비중",
        xaxis_title="날짜",
        yaxis_title="투자 비중",
        yaxis_tickformat=".0%",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=360,
    )

    return fig


# =========================
# 앱 본문
# =========================

st.title("₿ BTC 이동평균 분할진입 + 개선 매도 백테스트")

st.markdown(
    """
    **매수는 원안 유지**, 매도만 개선한 전략을 비교합니다.

    - 원안 매수: `5일선 > 120일선` 50%, `25일선 > 120일선` 75%, `99일선 > 120일선` 100%
    - 원안 매도: `5일선 < 120일선` 전량 매도
    - 개선 매도: `5일선 하락` 50% 축소, `25일선 하락` 25% 축소, `99일선 하락` 전량 매도
    """
)

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

    st.caption("예: 0.001 = 0.1%")

try:
    raw = download_price_data(ticker=ticker, start=str(start_date))
    df = add_moving_averages(raw)

    if trim_to_signal:
        df = df.dropna(subset=["ma120"]).copy()

    if df.empty:
        st.error("120일 이동평균 계산 이후 사용할 수 있는 데이터가 없습니다.")
        st.stop()

    df["original_position"] = calculate_original_position(df)
    df["improved_position"] = calculate_improved_position(df)

    original_bt = run_strategy_backtest(df, "original_position", fee_rate)
    improved_bt = run_strategy_backtest(df, "improved_position", fee_rate)
    buyhold_bt = run_buy_and_hold_backtest(df)

    metrics_df = pd.DataFrame(
        {
            "원안 전략": calculate_metrics(
                original_bt["equity"],
                original_bt["strategy_return"],
                original_bt["original_position"],
            ),
            "개선 매도 전략": calculate_metrics(
                improved_bt["equity"],
                improved_bt["strategy_return"],
                improved_bt["improved_position"],
            ),
            "BTC Buy & Hold": calculate_metrics(
                buyhold_bt["equity"],
                buyhold_bt["btc_return"],
                None,
            ),
        }
    ).T

    panel = pd.DataFrame(
        {
            "close": df["close"],
            "ma5": df["ma5"],
            "ma25": df["ma25"],
            "ma99": df["ma99"],
            "ma120": df["ma120"],
            "original_position": df["original_position"],
            "improved_position": df["improved_position"],
            "original_equity": original_bt["equity"],
            "improved_equity": improved_bt["equity"],
            "buyhold_equity": buyhold_bt["equity"],
            "original_return": original_bt["strategy_return"],
            "improved_return": improved_bt["strategy_return"],
            "buyhold_return": buyhold_bt["btc_return"],
            "cross_up_5": df["cross_up_5"],
            "cross_up_25": df["cross_up_25"],
            "cross_up_99": df["cross_up_99"],
            "cross_down_5": df["cross_down_5"],
            "cross_down_25": df["cross_down_25"],
            "cross_down_99": df["cross_down_99"],
        }
    )

    latest = df.iloc[-1]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("기준일", str(df.index[-1].date()))
    col2.metric("BTC 종가", f"{latest['close']:,.2f}")
    col3.metric("원안 현재 비중", f"{latest['original_position']:.0%}")
    col4.metric("개선 현재 비중", f"{latest['improved_position']:.0%}")

    st.subheader("성과 요약표")
    st.dataframe(
        make_display_metrics(metrics_df),
        use_container_width=True,
    )

    st.subheader("누적 수익률 그래프")
    st.plotly_chart(
        make_equity_chart(panel),
        use_container_width=True,
    )

    st.subheader("낙폭 그래프")
    st.plotly_chart(
        make_drawdown_chart(panel),
        use_container_width=True,
    )

    st.subheader("투자 비중 변화")
    st.plotly_chart(
        make_position_chart(panel),
        use_container_width=True,
    )

    st.subheader("일별 데이터")
    st.dataframe(
        panel.tail(500),
        use_container_width=True,
    )

    csv_metrics = metrics_df.to_csv(encoding="utf-8-sig")
    csv_panel = panel.to_csv(encoding="utf-8-sig")

    dl1, dl2 = st.columns(2)
    dl1.download_button(
        "성과표 CSV 다운로드",
        data=csv_metrics,
        file_name="btc_ma_strategy_metrics.csv",
        mime="text/csv",
    )
    dl2.download_button(
        "일별 백테스트 데이터 CSV 다운로드",
        data=csv_panel,
        file_name="btc_ma_strategy_panel.csv",
        mime="text/csv",
    )

except Exception as exc:
    st.error(f"실행 중 오류가 발생했습니다: {exc}")
