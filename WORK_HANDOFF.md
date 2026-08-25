# BTC 1분 추세신호 Telegram 알림 — 최종 인수인계

## 현재 상태

Firebase 예약 함수의 Blaze 결제를 피하기 위해 실제 운영 구조를 Cloudflare Workers Cron + D1으로 전환했다. 2026-08-25 기준 배포와 1분 실행, Binance 시세 처리, D1 상태 저장, Telegram API 전송이 성공했다.

- Repository: `eggT0928/bitcoin_backtest`
- Base: `main`
- 작업 branch: `feature/firebase-btc-telegram-alerts`
- PR: `#1`
- Worker: `btc-telegram-alerts`
- 배포 Version ID: `20e3bb09-5637-4f39-86fb-e98cc3b4737c`
- URL: `https://btc-telegram-alerts.btc-telegram-alerts-worker.workers.dev`
- Cron: `* * * * *`
- D1: `btc-telegram-alerts`
- D1 ID: `8ece5f02-d4bd-4476-a31a-8cb80aec593b`
- Telegram Bot: `@BTC_checker_bot`
- Secret 이름: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

Secret 값은 Cloudflare에만 저장되며 저장소와 대화에 노출하지 않았다.

## 구현

- Binance 글로벌 공개 `BTCUSDT` 1일봉 스트림을 매분 읽는다.
- D1 `market_candles`의 최근 130개 일봉을 현재 스트림 값으로 갱신한다.
- MA5 / MA20 / MA65 / MA120을 계산한다.
- MA5·20·65와 MA120 교차 순간 장중 미확정 알림을 한 번 생성한다.
- 같은 방향 3회 연속 관측 시 3분 유지 확인 알림을 한 번 생성한다.
- 마지막 확정 일봉 `closeTime`이 바뀌면 실제 실행이 09:01~09:02로 밀려도 종가 확정 알림을 한 번 생성한다.
- 같은 분 중복 실행은 `lastProcessedMinute`로 무시한다.
- D1 `alert_events` outbox의 고유 ID와 lease로 Telegram 중복 전송을 막는다.
- Telegram 실패 시 이벤트를 `pending`으로 되돌려 다음 실행에서 재시도한다.
- 자동 주문은 구현하지 않았다.

## 비중 state machine

현재 `position`을 D1 `alert_state`에 계속 저장하고 교차 이벤트가 생길 때만 변경한다.

- MA5 상향: `max(position, 0.50)`
- MA20 상향: `max(position, 0.75)`
- MA65 상향: `max(position, 1.00)`
- MA5 하향: `min(position, 0.50)`
- MA20 하향: `min(position, 0.25)`
- MA65 하향: `0.00`

`app.py`의 `calculate_event_position(..., sell_mode="partial")`과 같은 우선순위를 사용한다. 특히 MA20 하향 시 MA5가 아직 MA120 위여도 25% 이하로 줄어드는 테스트가 있다.

## 검증 결과

- `npm run check`: 성공
- `npm test`: 11/11 성공
- 테스트 항목: 변화 없음, 즉시 교차, 원복, 3분 유지, 중복 억제, 50→75→100% 상향, 50→25→0% 하향, 지연 일봉 확정, 같은 분 중복, Telegram 실패 재시도
- Cloudflare 배포: 성공
- Cron 1분 연속 실행: 성공
- 실행 로그 `outcome: ok`: 확인
- D1 `alert_state`: 매분 가격/MA/position 갱신 확인
- D1 시작 이벤트: `monitor-started-v1`, `status=sent`, `attempts=1`, 오류 없음
- 다음 연속 실행: `eventsCreated=0`으로 시작 알림 중복 없음
- Binance 확정 일봉 직접 비교:
  - price `78992.75`
  - MA5 `77032.972`
  - MA20 `67555.191`
  - MA65 `64554.08215384615`
  - MA120 `68360.31083333334`
  - Binance REST 원본과 D1 계산값 일치

Telegram API는 전송 성공을 반환했고, 사용자 화면에서 실제 메시지 확인만 마지막으로 기록하면 된다.

## 시세 연결 메모

Cloudflare 서버 IP에서 Binance REST 및 WebSocket API 요청은 지역 제한 `403/451`을 받았다. Binance API Key 문제는 아니다. 공식 market-data-only 실시간 스트림 `data-stream.binance.vision`은 정상 연결되므로, 최근 130개 일봉을 D1에 초기화하고 현재 일봉을 이 스트림으로 갱신하는 구조를 사용한다. Binance API Key나 계정 권한은 필요 없다.

## Firebase 메모

Google Cloud 프로젝트 `btc-telegram-alerts-260825`와 Firestore는 작업 중 생성됐으나 Billing을 연결하지 않았고 Functions도 배포하지 않았다. 운영에는 사용하지 않는다. 로컬 Firebase 배포 구성은 제거했으며 `firebase/README.md`에는 전환 사실만 남겼다.

## 남은 마무리

1. 사용자가 Telegram 시작 메시지를 실제 화면에서 확인했는지 기록한다.
2. 최종 보안 검색과 git diff를 검토한다.
3. PR #1 제목/본문을 Cloudflare 운영 구조에 맞게 갱신하고 검증 근거를 남긴다.
4. 모든 조건 확인 후에만 `main`에 병합한다.
