# BTC 현재가/MA120 Telegram 알림 — 인수인계

## 운영 구조

- Repository: `eggT0928/bitcoin_backtest`
- Worker: `btc-telegram-alerts`
- 배포 Version ID: `94322b68-c276-4227-94d7-bd1b16beb798` (2026-11-22)
- URL: `https://btc-telegram-alerts.btc-telegram-alerts-worker.workers.dev`
- Cron: 매 1분 (`* * * * *`)
- D1: `btc-telegram-alerts`
- D1 ID: `8ece5f02-d4bd-4476-a31a-8cb80aec593b`
- Telegram Bot: `@BTC_checker_bot`
- Secret: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- 시세: Binance 글로벌 공개 `BTCUSDT` 1일봉 스트림

Firebase 예약 함수는 비용 문제로 사용하지 않는다. Binance API Key와 자동 주문 권한도 사용하지 않는다.

## 매매 판단 규칙

전략 버전은 `price-ma120-v1`이다.

- 현재가가 MA120 아래에서 위로 전환: 즉시 `상승돌파` 알림, 비중 100%
- 현재가가 MA120 위에서 아래로 전환: 즉시 `하락돌파` 알림, 비중 0%
- MA5 / MA20 / MA65는 추세 참고값으로만 계산·표시
- MA5 / MA20 / MA65가 MA120을 교차해도 매매 알림이나 비중 변경 없음
- 1분 Cron이므로 실시간 돌파는 보통 1분 안에 감지

현재가와 MA120은 진행 중인 Binance 일봉을 포함해 계산한다. 같은 관계가 유지되는 동안에는 중복 알림을 보내지 않고, 실제로 반대편으로 다시 넘어갈 때 새 알림을 보낸다.

## Telegram 메시지

장중 돌파 알림에는 다음을 포함한다.

- 현재가와 MA120
- MA120 대비 현재가 등락률 (`+/-0.00%`)
- 매수 100% 또는 매도 0% 판단
- 추세 참고용 MA5 / MA20 / MA65
- 장중 미확정 신호 안내

일봉 종가 알림에는 다음을 포함한다.

- 종가와 MA120
- MA120 대비 종가 등락률 (`+/-0.00%`)
- 종가 기준 위/아래 판단과 새 종가 돌파 여부
- 추세 참고용 MA5 / MA20 / MA65 및 이평선 배열
- 현재 전략 비중

일봉 확정은 실행 시각이 아니라 마지막 확정 캔들의 `closeTime` 변경으로 감지하므로 09:01~09:02 지연에도 한 번만 전송한다.

## 상태 및 중복 방지

- D1 `alert_state`: `strategyVersion`, `priceAboveMa120`, `position`, 최근 가격/MA 저장
- D1 `alert_events`: 고유 이벤트 ID를 가진 Telegram outbox
- 같은 분 재실행: `lastProcessedMinute`로 중복 처리 방지
- 동시 전송: outbox lease로 중복 방지
- Telegram 실패: `pending`으로 되돌려 다음 실행에서 재시도
- 이전 MA 교차 전략 상태는 첫 실행 때 현재가/MA120 관계를 기준으로 한 번만 전환하며 과거 돌파를 새 돌파로 오인하지 않음

## 테스트

`cloudflare/test/signal-engine.test.js`의 10개 테스트가 다음을 검증한다.

- 변화 없음
- 현재가 MA120 상승돌파 즉시 알림 및 100%
- 현재가 MA120 하락돌파 즉시 알림 및 0%
- MA5·20·65 교차만으로는 알림 없음
- 같은 분 중복 실행 방지
- 기존 전략 상태의 안전한 전환
- 지연된 일봉 확정 및 종가 등락률
- 등락률 계산
- Telegram 실패 재시도
- Binance 일봉의 진행/확정 구분과 MA 계산

## 보안

Secret 값은 Cloudflare에만 저장한다. Token과 Chat ID를 소스, `.env`, GitHub, 대화에 남기지 않는다.
