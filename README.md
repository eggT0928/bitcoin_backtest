# BTC 이동평균 전략 비교 대시보드

## 문헌 기반 연구 업데이트 (2026-09-16)

주 분석은 **5/20/65/120**입니다. 기존 8개 전략과 Buy & Hold를 유지하고 사전등록한 연구 후보 3개를 비교합니다.
문헌 → 후보 고정 → 백테스트 순서와 commit 이력은 [연구 보고서](research/REPORT.md),
[문헌 표](research/LITERATURE.md), [사전등록](research/PREREGISTRATION.md), [변경 이력](research/AMENDMENTS.md)에 있습니다.

기본 자료는 **Coin Metrics UTC 일말 가격의 고정 스냅샷, 2026-05-23까지**입니다.
현재 네트워크에서 Yahoo 접근이 차단되어 성과 계산 전에 공급자를 변경했습니다. 실시간 가격이 아닙니다.
성과 시작은 모든 후보의 준비기간을 맞춘 2015-08-02, 기본 비용은 편도 0.1%입니다.
신호 다음 날 종가에 실행하고 실제 BTC 수량·현금을 추적합니다. 기존 성과 숫자와 달라질 수 있습니다.

```bash
pip install -r requirements-research.txt
python -m pytest -q
python run_research.py
python build_report.py
streamlit run app.py
```

신규 후보: 주간 가격–120일선 / 월말 가격–10개월선 / 주간 가격–변동성40%.
연구 후보 표시는 채택 권고가 아닙니다. 전체·국면·연도·비용·민감도와 회복기간을 함께 보세요.
대시보드는 기간 선택, 신규 투자/기존 경로 승계, 거래비용, 실행 지연, 최신 자료 기준 비중,
전체 성과표, 누적배율 로그·낙폭·실제 비중 그래프, 연도별 수익, 주문수·turnover와 CSV 다운로드를 제공합니다.

신호 코드는 `legacy_signals.py`, 실행/지표는 `backtest_engine.py`에 분리되어 있습니다.
기존 Telegram 알림 서비스는 이 연구 대시보드와 별도이며 이번 변경으로 자동매매나 알림 전략을 변경하지 않습니다.

비트코인 이동평균 전략을 표와 그래프로 확인하는 Streamlit 대시보드입니다.

## Telegram 실시간 알림

Binance BTCUSDT 일봉의 MA5·20·65와 MA120 교차를 1분마다 확인하는 Telegram 알림 서비스가 Cloudflare Workers + D1에 배포되어 있습니다. 자동 주문은 하지 않습니다.

배포 구조와 운영 방법은 [`cloudflare/README.md`](cloudflare/README.md)를 확인하세요.

## 비교 전략

| 전략 | 핵심 규칙 |
|---|---|
| 원안 전략 | 5/20/65일선 상향 돌파로 분할매수, 5일선 하향 돌파 시 전량 매도 |
| 개선 매도 전략 | 매수는 원안 유지, 5일선 하락 50%, 20일선 하락 25%, 65일선 하락 0% |
| 개선+2일 확인 | 개선 매도 전략에 2일 연속 확인 규칙 추가 |
| 개선+1% 완충 | 120일선 기준 ±1% 완충 구간을 두고 돌파 인정 |
| 개선+2일+1% 완충 | 2일 연속 확인과 ±1% 완충 구간을 함께 적용 |
| 개선+주 1회 판단 | 매일 판단하지 않고 주 1회, 일요일 종가 기준으로만 판단 |
| BTC Buy & Hold | 매수 후 보유 |

## 실행 방법

### GitHub Codespaces

```bash
pip install -r requirements.txt
streamlit run app.py
```

### 로컬 PC

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 대시보드에서 확인 가능한 항목

- 현재 전략별 투자 비중
- 성과 요약표
  - 최종배율
  - CAGR
  - MDD
  - 연변동성
  - Sharpe
  - Sortino
  - UPI
  - 평균투자비중
  - 거래횟수
  - 연평균회전율
  - 최장/평균 회복기간
- 누적 수익률 그래프
- Drawdown 그래프
- 투자 비중 변화 그래프
- 최근 일별 데이터
- CSV 다운로드
