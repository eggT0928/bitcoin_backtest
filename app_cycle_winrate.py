"""
BTC 추세추종·65일 모멘텀 하이브리드 백테스트 대시보드

실행:
streamlit run app_cycle_winrate.py
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


st.set_page_config(
    page_title="BTC 추세추종·모멘텀 전략 비교, 승률 포함",
    page_icon="₿",
    layout="wide",
)


# =========================
# 전략 파라미터
# =========================

BASE_MA = 120
FAST_MA = 5
MID_MA = 20
SLOW_MA = 65
PRICE_MOMENTUM_DAYS = 65

SIGNAL_MAS = [FAST_MA, MID_MA, SLOW_MA]
ALL_MAS = SIGNAL_MAS + [BASE_MA]

BUY_TARGETS = {
    FAST_MA: 0.50,
    MID_MA: 0.75,
    SLOW_MA: 1.00,
}

SELL_LIMITS = {
    FAST_MA: 0.50,
    MID_MA: 0.25,
    SLOW_MA: 0.00,
}

SCORE_POSITION_MAPS = {
    "linear": {
        0: 0.00,
        1: 0.25,
        2: 0.50,
        3: 0.75,
        4: 1.00,
    },
    "conservative": {
        0: 0.00,
        1: 0.00,
        2: 0.50,
        3: 0.75,
        4: 1.00,
    },
}

BUYHOLD_LABEL = "BTC Buy & Hold"


# =========================
# 전략 정의
# =========================

STRATEGIES = {
    "original": {
        "label": "원안 전략",
        "description": "5/20/65일선이 120일선을 상향 돌파할 때 분할매수, 5일선 하향 돌파 시 전량 매도",
        "strategy_type": "event",
        "sell_mode": "original",
        "confirm_days": 1,
        "buffer_pct": 0.0,
        "frequency": "daily",
    },
    "improved": {
        "label": "개선 매도 전략",
        "description": "5/20/65일선이 120일선을 상향 돌파할 때 분할매수, 5일선 하락 50%, 20일선 하락 25%, 65일선 하락 0%",
        "strategy_type": "event",
        "sell_mode": "partial",
        "confirm_days": 1,
        "buffer_pct": 0.0,
        "frequency": "daily",
    },
    "confirm2": {
        "label": "개선+2일 확인",
        "description": "5/20/65 개선 매도 전략에 2일 연속 확인 규칙 추가",
        "strategy_type": "event",
        "sell_mode": "partial",
        "confirm_days": 2,
        "buffer_pct": 0.0,
        "frequency": "daily",
    },
    "buffer1": {
        "label": "개선+1% 완충",
        "description": "5/20/65 개선 매도 전략에 120일선 기준 ±1% 완충 구간 적용",
        "strategy_type": "event",
        "sell_mode": "partial",
        "confirm_days": 1,
        "buffer_pct": 0.01,
        "frequency": "daily",
    },
    "confirm2_buffer1": {
        "label": "개선+2일+1% 완충",
        "description": "5/20/65 개선 매도 전략에 2일 연속 확인과 ±1% 완충 구간을 함께 적용",
        "strategy_type": "event",
        "sell_mode": "partial",
        "confirm_days": 2,
        "buffer_pct": 0.01,
        "frequency": "daily",
    },
    "weekly": {
        "label": "개선+주 1회 판단",
        "description": "5/20/65 개선 매도 전략을 매주 일요일 종가 기준으로만 판단",
        "strategy_type": "event",
        "sell_mode": "partial",
        "confirm_days": 1,
        "buffer_pct": 0.0,
        "frequency": "weekly",
    },
    "hybrid_score": {
        "label": "하이브리드 점수 전략",
        "description": "5일선>120일선, 20일선>120일선, 65일선>120일선, 현재가>65일 전 가격을 각각 1점으로 계산해 점수×25% 투자",
        "strategy_type": "score",
        "score_mode": "linear",
        "confirm_days": 1,
        "buffer_pct": 0.0,
        "frequency": "daily",
    },
    "hybrid_score_conservative": {
        "label": "하이브리드 보수형 점수 전략",
        "description": "4점 모멘텀 점수 중 0~1점은 현금, 2점 50%, 3점 75%, 4점 100% 투자",
        "strategy_type": "score",
        "score_mode": "conservative",
        "confirm_days": 1,
        "buffer_pct": 0.0,
        "frequency": "daily",
    },
}


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
# 이동평균, 모멘텀 점수 및 신호
# =========================

def add_moving_averages(df: pd.DataFrame) -> pd.DataFrame:
    """
    이동평균선을 계산합니다.
    """
    out = df.copy()

    for n in ALL_MAS:
        out[f"ma{n}"] = out["close"].rolling(n).mean()

    return out


def add_momentum_score(df: pd.DataFrame) -> pd.DataFrame:
    """
    5/20/65일선과 120일선, 65일 가격 모멘텀을 이용해 0~4점 모멘텀 점수를 계산합니다.
    """
    out = df.copy()

    out["score_ma5_120"] = (out[f"ma{FAST_MA}"] > out[f"ma{BASE_MA}"]).astype(int)
    out["score_ma20_120"] = (out[f"ma{MID_MA}"] > out[f"ma{BASE_MA}"]).astype(int)
    out["score_ma65_120"] = (out[f"ma{SLOW_MA}"] > out[f"ma{BASE_MA}"]).astype(int)
    out["score_price_65"] = (out["close"] > out["close"].shift(PRICE_MOMENTUM_DAYS)).astype(int)

    out["momentum_score"] = (
        out["score_ma5_120"]
        + out["score_ma20_120"]
        + out["score_ma65_120"]
        + out["score_price_65"]
    )

    return out


def calculate_score_position(df: pd.DataFrame, score_mode: str) -> pd.Series:
    """
    모멘텀 점수에 따라 투자 비중을 계산합니다.
    """
    if score_mode not in SCORE_POSITION_MAPS:
        raise ValueError(f"알 수 없는 score_mode입니다: {score_mode}")

    score_df = add_momentum_score(df)
    position = score_df["momentum_score"].map(SCORE_POSITION_MAPS[score_mode])

    return position.fillna(0.0).clip(lower=0.0, upper=1.0)


def state_signal(state: pd.Series, confirm_days: int) -> pd.Series:
    """
    조건이 confirm_days일 연속 성립한 첫날만 True로 만듭니다.
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
    """
    out = df.copy()
    upper = out[f"ma{BASE_MA}"] * (1.0 + buffer_pct)
    lower = out[f"ma{BASE_MA}"] * (1.0 - buffer_pct)

    for n in SIGNAL_MAS:
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
    if pd.isna(row[f"ma{BASE_MA}"]):
        return 0.0

    upper = row[f"ma{BASE_MA}"] * (1.0 + buffer_pct)
    position = 0.0

    for n in SIGNAL_MAS:
        if row[f"ma{n}"] > upper:
            position = max(position, BUY_TARGETS[n])

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
        if pd.isna(row[f"ma{BASE_MA}"]):
            positions.append(0.0)
            continue

        if not initialized:
            position = initial_position_from_state(row, buffer_pct)
            initialized = True

        major_risk_off = False

        # 매도 신호를 먼저 반영합니다.
        if sell_mode == "original":
            if row[f"cross_down_{FAST_MA}"]:
                position = 0.0
                major_risk_off = True
        elif sell_mode == "partial":
            if row[f"cross_down_{SLOW_MA}"]:
                position = SELL_LIMITS[SLOW_MA]
                major_risk_off = True
            elif row[f"cross_down_{MID_MA}"]:
                position = min(position, SELL_LIMITS[MID_MA])
            elif row[f"cross_down_{FAST_MA}"]:
                position = min(position, SELL_LIMITS[FAST_MA])
        else:
            raise ValueError(f"알 수 없는 sell_mode입니다: {sell_mode}")

        # 큰 위험 회피 신호가 나온 날에는 당일 매수 신호를 무시합니다.
        if not major_risk_off:
            for n in SIGNAL_MAS:
                if row[f"cross_up_{n}"]:
                    position = max(position, BUY_TARGETS[n])

        positions.append(position)

    return pd.Series(positions, index=signal_df.index)


def calculate_strategy_position(df: pd.DataFrame, config: dict) -> pd.Series:
    """
    전략 설정값에 따라 일별 투자 비중을 계산합니다.
    """
    strategy_type = config.get("strategy_type", "event")

    if strategy_type == "score":
        return calculate_score_position(df, score_mode=config["score_mode"]).reindex(df.index).fillna(0.0)

    frequency = config["frequency"]
    confirm_days = config["confirm_days"]
    buffer_pct = config["buffer_pct"]
    sell_mode = config["sell_mode"]

    if frequency == "daily":
        signal_df = add_cross_signals(df, confirm_days=confirm_days, buffer_pct=buffer_pct)
        position = calculate_event_position(signal_df, sell_mode=sell_mode, buffer_pct=buffer_pct)
        return position.reindex(df.index).fillna(0.0)

    if frequency == "weekly":
        weekly = df.resample("W-SUN").last().dropna(subset=["close"])
        weekly = add_cross_signals(weekly, confirm_days=confirm_days, buffer_pct=buffer_pct)
        weekly_position = calculate_event_position(weekly, sell_mode=sell_mode, buffer_pct=buffer_pct)
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


def calculate_trade_cycle_stats(equity: pd.Series, position: pd.Series) -> dict:
    """
    매매 사이클 승률을 계산합니다.

    정의:
    - 비중이 0% 이하에서 0% 초과로 올라간 날을 사이클 시작일로 봅니다.
    - 이후 비중이 다시 0% 이하가 되는 날을 완료 청산일로 봅니다.
    - 사이클 수익률은 청산일 equity / 진입 직전 equity - 1로 계산합니다.
    - 백테스트 종료 시점까지 0%로 돌아오지 않은 미완료 사이클은 승률 계산에서 제외합니다.
    """
    equity = equity.dropna()
    position = position.reindex(equity.index).fillna(0.0)

    completed_returns = []
    in_cycle = False
    entry_equity = np.nan

    prev_pos = 0.0
    for date in equity.index:
        current_pos = float(position.loc[date])

        if not in_cycle and prev_pos <= 0.0 and current_pos > 0.0:
            in_cycle = True
            entry_equity = float(equity.shift(1).reindex(equity.index).loc[date])
            if np.isnan(entry_equity):
                entry_equity = float(equity.loc[date])

        elif in_cycle and current_pos <= 0.0:
            exit_equity = float(equity.loc[date])
            if entry_equity > 0:
                completed_returns.append(exit_equity / entry_equity - 1.0)
            in_cycle = False
            entry_equity = np.nan

        prev_pos = current_pos

    completed_count = len(completed_returns)
    open_cycles = 1 if in_cycle else 0

    if completed_count == 0:
        return {
            "완료매매수": 0,
            "미완료매매수": open_cycles,
            "승률": np.nan,
            "평균승리수익률": np.nan,
            "평균패배수익률": np.nan,
            "손익비": np.nan,
        }

    returns = pd.Series(completed_returns, dtype=float)
    wins = returns[returns > 0]
    losses = returns[returns <= 0]

    win_rate = len(wins) / completed_count
    avg_win = wins.mean() if len(wins) > 0 else np.nan
    avg_loss = losses.mean() if len(losses) > 0 else np.nan
    profit_loss_ratio = np.nan

    if pd.notna(avg_win) and pd.notna(avg_loss) and avg_loss != 0:
        profit_loss_ratio = avg_win / abs(avg_loss)

    return {
        "완료매매수": completed_count,
        "미완료매매수": open_cycles,
        "승률": win_rate,
        "평균승리수익률": avg_win,
        "평균패배수익률": avg_loss,
        "손익비": profit_loss_ratio,
    }


def calculate_metrics(
    equity: pd.Series,
    returns: pd.Series,
    position: Optional[pd.Series] = None,
) -> dict:
    """
    CAGR, MDD, 변동성, 샤프, 소르티노, UPI, 매매 사이클 승률 등을 계산합니다.
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
    cycle_stats = {
        "완료매매수": np.nan,
        "미완료매매수": np.nan,
        "승률": np.nan,
        "평균승리수익률": np.nan,
        "평균패배수익률": np.nan,
        "손익비": np.nan,
    }

    if position is not None:
        position = position.reindex(equity.index).fillna(0.0)
        position_change = position.diff().fillna(0.0)
        avg_position = position.mean()
        trade_count = int((position_change.abs() > 0).sum())
        turnover_per_year = position_change.abs().sum() / years if years > 0 else np.nan
        cycle_stats = calculate_trade_cycle_stats(equity, position)

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
        **cycle_stats,
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

    percent_cols = [
        "CAGR",
        "MDD",
        "연변동성",
        "평균투자비중",
        "연평균회전율",
        "승률",
        "평균승리수익률",
        "평균패배수익률",
    ]
    for col in percent_cols:
        if col in display.columns:
            display[col] = display[col].map(format_percent)

    number_cols = [
        "최종배율",
        "Sharpe",
        "Sortino",
        "UPI",
        "거래횟수",
        "완료매매수",
        "미완료매매수",
        "손익비",
        "최장회복기간_일",
        "평균회복기간_일",
    ]
    for col in number_cols:
        if col in display.columns:
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
        fig.add_trace(go.Scatter(x=equity_panel.index, y=equity_panel[label], mode="lines", name=label))

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
        fig.add_trace(go.Scatter(x=equity_panel.index, y=drawdown, mode="lines", name=label))

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
        fig.add_trace(go.Scatter(x=position_panel.index, y=position_panel[label], mode="lines", name=label))

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


def make_score_chart(score_df: pd.DataFrame) -> go.Figure:
    """
    하이브리드 모멘텀 점수 그래프를 만듭니다.
    """
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=score_df.index, y=score_df["momentum_score"], mode="lines", name="모멘텀 점수"))
    fig.update_layout(
        title="하이브리드 모멘텀 점수, 0~4점",
        xaxis_title="날짜",
        yaxis_title="점수",
        yaxis=dict(range=[-0.1, 4.1], dtick=1),
        hovermode="x unified",
        height=320,
    )
    return fig


# =========================
# 앱 본문
# =========================

st.title("₿ BTC 추세추종·65일 모멘텀 하이브리드 전략 비교")

st.markdown(
    """
    120일선을 기준선으로 두는 **5·20·65 이동평균 추세추종 전략**과,
    여기에 **65일 가격 모멘텀**을 섞은 하이브리드 점수 전략을 함께 비교합니다.

    이번 버전은 성과표에 **매매 사이클 승률**을 추가했습니다.
    매매 사이클은 **비중이 0%에서 시작해 다시 0%로 돌아올 때까지**를 1회로 계산합니다.
    """
)

with st.expander("전략 규칙 보기", expanded=False):
    strategy_info = pd.DataFrame(
        [
            {
                "전략": cfg["label"],
                "설명": cfg["description"],
                "유형": "점수형" if cfg.get("strategy_type") == "score" else "돌파형",
                "확인일수": cfg.get("confirm_days", ""),
                "완충구간": f"{cfg.get('buffer_pct', 0.0):.1%}",
                "판단주기": "매일" if cfg.get("frequency") == "daily" else "주 1회",
            }
            for cfg in STRATEGIES.values()
        ]
    )
    st.dataframe(strategy_info, use_container_width=True)

with st.expander("성과표 승률 지표 정의", expanded=False):
    st.markdown(
        """
        - **완료매매수**: 0% → 투자 시작 → 다시 0% 청산까지 완료된 사이클 수
        - **미완료매매수**: 백테스트 마지막 날까지 아직 0%로 청산되지 않은 열린 사이클 수
        - **승률**: 완료매매수 중 수익률이 0% 초과인 사이클 비율
        - **평균승리수익률**: 수익 난 완료 사이클의 평균 수익률
        - **평균패배수익률**: 손실 또는 0% 이하 완료 사이클의 평균 수익률
        - **손익비**: 평균승리수익률 ÷ 평균패배수익률의 절댓값
        """
    )

with st.expander("하이브리드 점수 비중 규칙 보기", expanded=False):
    score_rule = pd.DataFrame(
        [
            {"점수": "0점", "기본형 비중": "0%", "보수형 비중": "0%"},
            {"점수": "1점", "기본형 비중": "25%", "보수형 비중": "0%"},
            {"점수": "2점", "기본형 비중": "50%", "보수형 비중": "50%"},
            {"점수": "3점", "기본형 비중": "75%", "보수형 비중": "75%"},
            {"점수": "4점", "기본형 비중": "100%", "보수형 비중": "100%"},
        ]
    )
    st.dataframe(score_rule, use_container_width=True)

with st.expander("기존 5·20·65 / 120일선 돌파형 비중 규칙 보기", expanded=False):
    weight_rule = pd.DataFrame(
        [
            {"구분": "매수", "조건": "5일선 > 120일선", "목표/제한 비중": "50%"},
            {"구분": "매수", "조건": "20일선 > 120일선", "목표/제한 비중": "75%"},
            {"구분": "매수", "조건": "65일선 > 120일선", "목표/제한 비중": "100%"},
            {"구분": "매도", "조건": "5일선 < 120일선", "목표/제한 비중": "최대 50%"},
            {"구분": "매도", "조건": "20일선 < 120일선", "목표/제한 비중": "최대 25%"},
            {"구분": "매도", "조건": "65일선 < 120일선", "목표/제한 비중": "0%"},
        ]
    )
    st.dataframe(weight_rule, use_container_width=True)

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
        "개선 매도 전략",
        "개선+주 1회 판단",
        "하이브리드 점수 전략",
        "하이브리드 보수형 점수 전략",
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
        df = df.dropna(subset=[f"ma{BASE_MA}"]).copy()

    if df.empty:
        st.error("120일 이동평균 계산 이후 사용할 수 있는 데이터가 없습니다.")
        st.stop()

    score_df = add_momentum_score(df)

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
    latest_score = score_df.iloc[-1]
    latest_positions = position_panel.iloc[-1]

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("기준일", str(df.index[-1].date()))
    col2.metric("BTC 종가", f"{latest['close']:,.2f}")
    col3.metric(
        "5/20/65/120일선",
        f"{latest['ma5']:,.0f} / {latest['ma20']:,.0f} / {latest['ma65']:,.0f} / {latest['ma120']:,.0f}",
    )
    col4.metric("현재 모멘텀 점수", f"{int(latest_score['momentum_score'])} / 4점")
    col5.metric("거래비용", f"{fee_rate:.2%}")

    st.subheader("현재 모멘텀 점수 세부 조건")
    current_score_detail = pd.DataFrame(
        [
            {"조건": "5일선 > 120일선", "충족 여부": "예" if latest_score["score_ma5_120"] == 1 else "아니오", "점수": int(latest_score["score_ma5_120"])},
            {"조건": "20일선 > 120일선", "충족 여부": "예" if latest_score["score_ma20_120"] == 1 else "아니오", "점수": int(latest_score["score_ma20_120"])},
            {"조건": "65일선 > 120일선", "충족 여부": "예" if latest_score["score_ma65_120"] == 1 else "아니오", "점수": int(latest_score["score_ma65_120"])},
            {"조건": "현재가 > 65일 전 가격", "충족 여부": "예" if latest_score["score_price_65"] == 1 else "아니오", "점수": int(latest_score["score_price_65"])},
        ]
    )
    st.dataframe(current_score_detail, use_container_width=True)

    st.subheader("현재 전략별 투자 비중")
    current_position_df = pd.DataFrame({"현재 비중": latest_positions})
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

    st.subheader("하이브리드 모멘텀 점수 변화")
    st.plotly_chart(make_score_chart(score_df), use_container_width=True)

    st.subheader("최근 일별 데이터")
    daily_panel = pd.concat(
        [
            df[["close", "ma5", "ma20", "ma65", "ma120"]],
            score_df[["score_ma5_120", "score_ma20_120", "score_ma65_120", "score_price_65", "momentum_score"]],
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
        file_name="btc_strategy_compare_metrics_with_winrate.csv",
        mime="text/csv",
    )
    dl2.download_button(
        "일별 백테스트 데이터 CSV 다운로드",
        data=csv_daily,
        file_name="btc_strategy_compare_daily_with_winrate.csv",
        mime="text/csv",
    )

except Exception as exc:
    st.error(f"실행 중 오류가 발생했습니다: {exc}")
