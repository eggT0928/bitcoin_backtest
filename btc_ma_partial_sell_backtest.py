"""
BTC 이동평균 분할진입 + 개선 매도 전략 백테스트

전략 요약
1) 매수 규칙, 원안 유지
- 5일선이 120일선 상향 돌파: 50% 투자
- 25일선이 120일선 상향 돌파: 75% 투자
- 99일선이 120일선 상향 돌파: 100% 투자

2) 원안 매도 규칙
- 5일선이 120일선 하향 돌파: 전량 매도

3) 개선 매도 규칙
- 5일선이 120일선 하향 돌파: 50%로 축소
- 25일선이 120일선 하향 돌파: 25%로 축소
- 99일선이 120일선 하향 돌파: 전량 매도

실행 전 설치
pip install yfinance pandas numpy matplotlib openpyxl

실행
python btc_ma_partial_sell_backtest.py
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# =========================
# 사용자 설정값
# =========================

TICKER = "BTC-USD"
START_DATE = "2014-09-17"
END_DATE = None
# 비중이 1.0만큼 바뀔 때 차감할 거래비용입니다.
# 예: 0.001 = 0.1%
FEE_RATE = 0.001

# 최초 120일선이 계산되는 시점부터 성과를 비교합니다.
TRIM_TO_FIRST_VALID_SIGNAL = True

# 결과 저장 폴더
OUTPUT_DIR = Path("btc_ma_strategy_output")


# =========================
# 데이터 구조
# =========================

@dataclass
class BacktestResult:
    name: str
    data: pd.DataFrame
    metrics: dict


# =========================
# 데이터 다운로드
# =========================

def download_price_data(
    ticker: str = TICKER,
    start: str = START_DATE,
    end: Optional[str] = END_DATE,
) -> pd.DataFrame:
    """
    yfinance에서 가격 데이터를 다운로드합니다.
    """
    try:
        import yfinance as yf
    except ImportError as exc:
        raise ImportError(
            "yfinance가 설치되어 있지 않습니다. 먼저 아래 명령어를 실행하세요.\n"
            "pip install yfinance pandas numpy matplotlib openpyxl"
        ) from exc

    df = yf.download(
        ticker,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
    )

    if df.empty:
        raise ValueError(
            "가격 데이터를 불러오지 못했습니다. 인터넷 연결, 티커, yfinance 설치 상태를 확인하세요."
        )

    # yfinance 버전에 따라 MultiIndex 컬럼으로 들어오는 경우 처리합니다.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    if "Close" not in df.columns:
        raise ValueError("다운로드 데이터에서 Close 컬럼을 찾지 못했습니다.")

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

    # 상향 돌파: 어제는 같거나 아래, 오늘은 위
    out["cross_up_5"] = (out["ma5"] > out["ma120"]) & (
        out["ma5"].shift(1) <= out["ma120"].shift(1)
    )
    out["cross_up_25"] = (out["ma25"] > out["ma120"]) & (
        out["ma25"].shift(1) <= out["ma120"].shift(1)
    )
    out["cross_up_99"] = (out["ma99"] > out["ma120"]) & (
        out["ma99"].shift(1) <= out["ma120"].shift(1)
    )

    # 하향 돌파: 어제는 같거나 위, 오늘은 아래
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

        # 매도 신호를 먼저 반영합니다.
        if row["cross_down_5"]:
            position = 0.0

        # 매수 신호를 반영합니다.
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

        # 매도 신호를 먼저 반영합니다.
        # 하향 돌파가 여러 개 동시에 발생할 경우 가장 강한 매도 조건을 우선합니다.
        if row["cross_down_99"]:
            position = 0.0

        elif row["cross_down_25"]:
            position = min(position, 0.25)

        elif row["cross_down_5"]:
            position = min(position, 0.50)

        # 매수 신호를 반영합니다.
        if row["cross_up_5"]:
            position = max(position, 0.50)

        if row["cross_up_25"]:
            position = max(position, 0.75)

        if row["cross_up_99"]:
            position = max(position, 1.00)

        positions.append(position)

    return pd.Series(positions, index=df.index, name="improved_position")


# =========================
# 백테스트 계산
# =========================

def run_strategy_backtest(
    df: pd.DataFrame,
    position_col: str,
    fee_rate: float = FEE_RATE,
) -> pd.DataFrame:
    """
    전략 수익률과 평가금 흐름을 계산합니다.

    룩어헤드 방지:
    - 오늘 종가 기준으로 신호를 확인했다고 가정합니다.
    - 따라서 오늘 계산된 비중은 다음 날 수익률부터 적용합니다.
    """
    out = df.copy()

    out["btc_return"] = out["close"].pct_change().fillna(0.0)
    out["applied_position"] = out[position_col].shift(1).fillna(0.0)

    # 비중 변화량만큼 거래비용을 차감합니다.
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
# 성과지표 계산
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

    # 마지막까지 회복하지 못한 구간도 현재까지의 진행 기간으로 기록합니다.
    if start_date is not None:
        periods.append((equity.index[-1] - start_date).days)

    if not periods:
        return {
            "최장회복기간_일": 0,
            "평균회복기간_일": 0,
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

    if len(equity) < 2:
        raise ValueError("성과지표를 계산하기 위한 데이터가 부족합니다.")

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


def format_metrics_for_print(metrics_df: pd.DataFrame) -> pd.DataFrame:
    """
    콘솔 출력용 성과표를 만듭니다.
    """
    formatted = metrics_df.copy()

    percent_cols = [
        "CAGR",
        "MDD",
        "연변동성",
        "평균투자비중",
        "연평균회전율",
    ]

    for col in percent_cols:
        formatted[col] = formatted[col].map(
            lambda x: "" if pd.isna(x) else f"{x:.2%}"
        )

    number_cols = [
        "최종배율",
        "Sharpe",
        "Sortino",
        "UPI",
        "거래횟수",
        "최장회복기간_일",
        "평균회복기간_일",
    ]

    for col in number_cols:
        formatted[col] = formatted[col].map(
            lambda x: "" if pd.isna(x) else f"{x:.2f}"
        )

    return formatted


# =========================
# 그래프 저장
# =========================

def save_equity_curve_chart(
    original_bt: pd.DataFrame,
    improved_bt: pd.DataFrame,
    buyhold_bt: pd.DataFrame,
    output_path: Path,
) -> None:
    """
    누적수익률 그래프를 저장합니다.
    """
    plt.figure(figsize=(12, 6))
    plt.plot(original_bt.index, original_bt["equity"], label="Original")
    plt.plot(improved_bt.index, improved_bt["equity"], label="Improved Sell")
    plt.plot(buyhold_bt.index, buyhold_bt["equity"], label="BTC Buy & Hold")
    plt.yscale("log")
    plt.title("BTC MA Strategy Equity Curve")
    plt.xlabel("Date")
    plt.ylabel("Equity, Log Scale")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def save_drawdown_chart(
    original_bt: pd.DataFrame,
    improved_bt: pd.DataFrame,
    buyhold_bt: pd.DataFrame,
    output_path: Path,
) -> None:
    """
    낙폭 그래프를 저장합니다.
    """
    plt.figure(figsize=(12, 6))

    for bt, label in [
        (original_bt, "Original"),
        (improved_bt, "Improved Sell"),
        (buyhold_bt, "BTC Buy & Hold"),
    ]:
        drawdown = bt["equity"] / bt["equity"].cummax() - 1
        plt.plot(bt.index, drawdown, label=label)

    plt.title("BTC MA Strategy Drawdown")
    plt.xlabel("Date")
    plt.ylabel("Drawdown")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def save_position_chart(
    df: pd.DataFrame,
    output_path: Path,
) -> None:
    """
    원안 전략과 개선 매도 전략의 비중 변화를 저장합니다.
    """
    plt.figure(figsize=(12, 4))
    plt.plot(df.index, df["original_position"], label="Original Position")
    plt.plot(df.index, df["improved_position"], label="Improved Position")
    plt.title("Strategy Position")
    plt.xlabel("Date")
    plt.ylabel("Position")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


# =========================
# 메인 실행
# =========================

def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("BTC 가격 데이터를 다운로드합니다...")
    df = download_price_data()
    df = add_moving_averages(df)

    if TRIM_TO_FIRST_VALID_SIGNAL:
        df = df.dropna(subset=["ma120"]).copy()

    if df.empty:
        raise ValueError("120일 이동평균 계산 이후 사용할 수 있는 데이터가 없습니다.")

    df["original_position"] = calculate_original_position(df)
    df["improved_position"] = calculate_improved_position(df)

    original_bt = run_strategy_backtest(df, "original_position", FEE_RATE)
    improved_bt = run_strategy_backtest(df, "improved_position", FEE_RATE)
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

    print("\n===== 성과 비교 =====")
    print(format_metrics_for_print(metrics_df).to_string())

    latest = df.iloc[-1]

    print("\n===== 현재 상태 =====")
    print(f"기준일: {df.index[-1].date()}")
    print(f"BTC 종가: {latest['close']:,.2f}")
    print(f"5일선: {latest['ma5']:,.2f}")
    print(f"25일선: {latest['ma25']:,.2f}")
    print(f"99일선: {latest['ma99']:,.2f}")
    print(f"120일선: {latest['ma120']:,.2f}")
    print(f"원안 전략 현재 비중: {latest['original_position']:.0%}")
    print(f"개선 매도 전략 현재 비중: {latest['improved_position']:.0%}")

    output_panel = pd.DataFrame(
        {
            "close": df["close"],
            "ma5": df["ma5"],
            "ma25": df["ma25"],
            "ma99": df["ma99"],
            "ma120": df["ma120"],
            "cross_up_5": df["cross_up_5"],
            "cross_up_25": df["cross_up_25"],
            "cross_up_99": df["cross_up_99"],
            "cross_down_5": df["cross_down_5"],
            "cross_down_25": df["cross_down_25"],
            "cross_down_99": df["cross_down_99"],
            "original_position": df["original_position"],
            "improved_position": df["improved_position"],
            "original_equity": original_bt["equity"],
            "improved_equity": improved_bt["equity"],
            "buyhold_equity": buyhold_bt["equity"],
            "original_return": original_bt["strategy_return"],
            "improved_return": improved_bt["strategy_return"],
            "buyhold_return": buyhold_bt["btc_return"],
        }
    )

    # CSV와 엑셀 저장
    output_panel.to_csv(
        OUTPUT_DIR / "btc_ma_strategy_backtest_panel.csv",
        encoding="utf-8-sig",
    )
    metrics_df.to_csv(
        OUTPUT_DIR / "btc_ma_strategy_metrics.csv",
        encoding="utf-8-sig",
    )

    with pd.ExcelWriter(OUTPUT_DIR / "btc_ma_strategy_backtest.xlsx", engine="openpyxl") as writer:
        metrics_df.to_excel(writer, sheet_name="metrics")
        output_panel.to_excel(writer, sheet_name="daily_panel")

    # 그래프 저장
    save_equity_curve_chart(
        original_bt,
        improved_bt,
        buyhold_bt,
        OUTPUT_DIR / "equity_curve_log.png",
    )
    save_drawdown_chart(
        original_bt,
        improved_bt,
        buyhold_bt,
        OUTPUT_DIR / "drawdown.png",
    )
    save_position_chart(
        df,
        OUTPUT_DIR / "position.png",
    )

    print("\n===== 파일 저장 완료 =====")
    print(f"저장 폴더: {OUTPUT_DIR.resolve()}")
    print("- btc_ma_strategy_metrics.csv")
    print("- btc_ma_strategy_backtest_panel.csv")
    print("- btc_ma_strategy_backtest.xlsx")
    print("- equity_curve_log.png")
    print("- drawdown.png")
    print("- position.png")


if __name__ == "__main__":
    main()
