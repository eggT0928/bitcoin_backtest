"""Original main 1654d04 signal logic, preserved separately from execution/accounting."""

from __future__ import annotations

import numpy as np

import pandas as pd

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

    점수 조건:
    - 5일선 > 120일선: +1점
    - 20일선 > 120일선: +1점
    - 65일선 > 120일선: +1점
    - 현재가 > 65일 전 가격: +1점
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
    confirm_days=1이면 일반적인 상태 전환 신호와 같습니다.
    """
    state = state.fillna(False).astype(bool)

    if confirm_days <= 1:
        confirmed = state
    else:
        confirmed = state.rolling(confirm_days).sum().eq(confirm_days).fillna(False)

    # Explicit bool avoids pandas 3 object inversion; event definition is unchanged.
    return confirmed & ~confirmed.shift(1).fillna(False).astype(bool)

def add_cross_signals(
    df: pd.DataFrame,
    confirm_days: int = 1,
    buffer_pct: float = 0.0,
) -> pd.DataFrame:
    """
    상향/하향 돌파 신호를 계산합니다.

    buffer_pct=0.01이면:
    - 상향 돌파 인정 기준: 단기선 > 기준선 * 1.01
    - 하향 돌파 인정 기준: 단기선 < 기준선 * 0.99
    - 그 사이 구간은 기존 비중 유지
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

    보수형 처리:
    - 65일선이 120일선을 하향 돌파한 날은 중기 추세 훼손으로 보고 당일 매수 신호를 무시합니다.
    - 원안 전략에서 5일선 하향 돌파로 전량 매도한 날도 당일 매수 신호를 무시합니다.
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
        # 비트코인은 매일 거래되므로 일요일 데이터를 주간 판단일로 사용합니다.
        # 주식형 티커처럼 일요일 데이터가 없는 경우를 대비해 W-SUN의 마지막 관측값을 사용합니다.
        weekly = df.resample("W-SUN").last().dropna(subset=["close"])
        weekly = add_cross_signals(weekly, confirm_days=confirm_days, buffer_pct=buffer_pct)
        weekly_position = calculate_event_position(weekly, sell_mode=sell_mode, buffer_pct=buffer_pct)

        # 주간 판단일에 결정된 비중을 다음 판단일까지 유지합니다.
        position = weekly_position.reindex(df.index, method="ffill").fillna(0.0)
        return position

    raise ValueError(f"알 수 없는 frequency입니다: {frequency}")
