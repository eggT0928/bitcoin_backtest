# Work 인수인계 — BTC 1분 추세신호 Telegram 알림

## 1. 프로젝트 목표

기존 `bitcoin_backtest`의 5/20/65일선 vs 120일선 전략을 기반으로, BTCUSDT 일봉 신호를 1분 단위로 감시하고 Telegram으로 알림을 보내는 운영용 시스템을 완성한다.

사용자가 원하는 최종 동작:

- Binance `BTCUSDT` 사용
- 1분마다 감시
- MA5 / MA20 / MA65 / MA120 계산
- MA5·20·65가 MA120을 상향/하향 교차하는 순간 장중 즉시 알림
- 같은 방향으로 3분 연속 유지되면 확인 알림
- 새 일봉이 확정되면 종가 기준 확정 신호 알림
- Firestore에 상태 저장 및 중복 알림 방지
- Telegram Bot으로 개인 알림
- 자동 주문 기능은 넣지 않음

## 2. GitHub 상태

- Repository: `eggT0928/bitcoin_backtest`
- Base branch: `main`
- 작업 branch: `feature/firebase-btc-telegram-alerts`
- PR: `#1 Add Firebase 1-minute BTC Telegram signal alerts`
- PR은 현재 open 상태이며 main에 아직 merge하지 않았다.

Work에서는 먼저 위 branch와 PR을 읽고, **새로 처음부터 만들지 말고 현재 구현을 이어서 수정·검증·배포**한다.

## 3. 현재 추가된 파일

- `firebase.json`
  - Functions source: `firebase/functions`
  - Node.js 20
  - region: `asia-northeast3`

- `firebase/functions/package.json`
  - `firebase-admin`
  - `firebase-functions`
  - Node 20
  - lint는 `node --check index.js`

- `firebase/functions/index.js`
  - Firebase Functions 2nd gen `onSchedule`
  - `* * * * *` 1분 스케줄
  - Binance REST `api/v3/klines`, `interval=1d`, `limit=130`
  - 진행 중 일봉을 포함한 실시간 MA 계산
  - Firestore `btcAlerts/state`
  - Telegram Bot API `sendMessage`
  - 최초 장중 교차 즉시 알림
  - 3회 연속 관측(약 3분) 후 유지 확인 알림
  - 일봉 확정 요약 알림

- `firebase/README.md`
  - Firebase / Telegram 설정 및 배포 방법 초안

## 4. 기존 전략 규칙

기존 Streamlit 앱(`app.py`)의 이벤트 기반 개선 매도 전략을 기준으로 운영 신호를 맞춘다.

상향 교차 시 목표 비중:

- MA5 ↑ MA120 → 50%
- MA20 ↑ MA120 → 75%
- MA65 ↑ MA120 → 100%

하향 교차 시 제한 비중:

- MA5 ↓ MA120 → 최대 50%
- MA20 ↓ MA120 → 최대 25%
- MA65 ↓ MA120 → 0%

중요: 이는 단순히 현재 MA 관계만 보고 `max()`로 비중을 재계산하는 정적 규칙이 아니라 **이벤트 기반 상태 전이 전략**이다.

## 5. 배포 전 반드시 수정/검증할 항목

### A. 현재 `targetPosition(rel)`의 하향 교차 처리 불일치

현재 Firebase 코드의 `targetPosition(rel)`은 MA5/20/65 중 MA120 위에 있는 가장 높은 매수 목표 비중을 반환한다.

이 방식은 상향 교차에는 맞지만, 기존 앱의 부분매도 규칙과 완전히 같지 않다.

예:

- MA20이 MA120 아래로 하향 교차
- MA5는 여전히 MA120 위

기존 앱의 이벤트 전략은 비중을 **최대 25%**로 낮춰야 하지만, 현재 Firebase의 정적 관계 계산은 MA5가 위라는 이유로 **50%**를 반환할 수 있다.

따라서 production 배포 전에 반드시:

- Firestore에 현재 전략 비중(`position`)을 상태로 저장하고
- 교차 이벤트별로 비중을 상태 전이 방식으로 갱신
- 상향: `max(currentPosition, BUY_TARGET)`
- 하향: `min(currentPosition, SELL_LIMIT)`
- 기존 `app.py`의 `calculate_event_position()` 동작과 동일한지 테스트

하도록 수정한다.

### B. 오전 09:00 정확한 분에만 일봉 확정 알림을 보내는 로직 개선

현재 코드는 KST `09:00`일 때만 확정 일봉 요약을 전송한다.

Cloud Scheduler 실행이 1~2분 지연되면 09:00 조건을 놓칠 수 있으므로, 더 견고하게 변경한다.

권장 방식:

- `closed.candleCloseTime` 또는 마지막 확정 캔들의 `openTime/closeTime`을 Firestore에 저장
- 이전에 처리한 확정 캔들 ID와 달라졌을 때만 일봉 확정 알림 전송
- 실제 함수 실행 시각이 09:01 또는 09:02여도 새 일봉 확정을 놓치지 않게 한다.

### C. 최초 배포 시 상태 초기화 정책

최초 실행 시 현재 관계를 기준 상태로 잡아 과거 교차를 새 신호처럼 알리지 않도록 하는 것은 적절하다.

다만 최초 상태에 대해:

- 현재 MA 값
- 현재 관계
- 전략상 초기 비중

을 Firestore에 명시적으로 기록하고, 필요하면 Telegram에 `모니터링 시작` 1회 메시지를 보내는 옵션을 검토한다.

### D. 중복 실행 / 동시성

현재 `lastProcessedMinute`를 Firestore transaction으로 claim하는 방식이 들어가 있다.

다음 항목을 테스트한다.

- 같은 분에 Functions가 중복 실행되어도 Telegram 중복 알림이 없는지
- 3분 유지 카운트가 중복 실행 때문에 2번 증가하지 않는지
- Telegram 전송 실패 후 재시도 시 상태/알림이 유실 또는 중복되지 않는지

가능하면 알림 이벤트 ID를 Firestore에 기록해 idempotency를 강화한다.

## 6. Firebase에서 해야 할 실제 작업

가능한 경우 Work/Codex 환경에서 사용자의 인증된 Google Cloud/Firebase 계정으로 직접 수행한다. 직접 계정 조작 권한이 없는 단계만 사용자에게 최소한으로 요청한다.

필요 작업:

1. Firebase/Google Cloud 프로젝트 생성 또는 기존 프로젝트 선택
2. Billing(Blaze) 연결 여부 확인
3. Firestore Database 생성
4. 필요한 API / Scheduler / Functions 권한 확인
5. 저장소에 `.firebaserc` 또는 프로젝트 연결 설정 추가
6. Telegram Bot 준비
7. `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`를 Firebase Secret Manager에 등록
8. `npm install`
9. lint / 로컬 단위 검증
10. Functions 배포
11. Cloud Scheduler가 매 1분 생성되었는지 확인
12. Functions 로그 확인
13. Telegram 테스트 메시지 수신 확인
14. Firestore `btcAlerts/state` 생성/갱신 확인
15. 실제 MA 계산을 Binance 원데이터와 비교 검증

## 7. Telegram 보안 규칙

- Bot Token을 채팅, GitHub source, README, `.env` 커밋에 남기지 않는다.
- Secret Manager/Firebase Functions secrets를 사용한다.
- 사용자가 채팅에 Bot Token을 붙여 넣도록 유도하지 않는다.
- Chat ID도 Secret으로 관리하는 현재 구조를 유지해도 된다.

## 8. 검증해야 할 테스트 시나리오

최소 다음을 테스트한다.

1. 평상시 관계 변화 없음 → Telegram 알림 없음
2. MA5 아래→위 → 즉시 미확정 알림 1회
3. 1분 뒤 원복 → 3분 유지 알림 없음
4. 3분 연속 유지 → 확인 알림 1회
5. 같은 상태 지속 → 추가 중복 알림 없음
6. MA20 상향 교차 → 비중 50→75%
7. MA65 상향 교차 → 비중 75→100%
8. MA5 하향 → 최대 50%
9. MA20 하향 → 최대 25%
10. MA65 하향 → 0%
11. 새 UTC 일봉 종료(KST 오전 9시 전후) → 실행 지연과 무관하게 확정 알림 1회
12. Functions 중복 invocation → 중복 Telegram 없음
13. Telegram 일시 실패 → 오류 로그와 재시도 정책 확인

실제 시장에서 교차를 기다리지 않고, 신호 계산 함수를 순수 함수로 분리해서 테스트 입력으로 검증하는 것을 권장한다.

## 9. 완료 기준

다음을 모두 만족해야 완료로 본다.

- 1분 스케줄이 실제 Firebase에 배포됨
- Binance BTCUSDT를 기준으로 MA5/20/65/120 계산됨
- 장중 교차 즉시 알림 동작
- 3분 유지 확인 동작
- 일봉 확정 알림을 스케줄 지연에도 놓치지 않음
- 상·하향 이벤트에 따른 비중 전이가 기존 `app.py` 전략과 일치
- Firestore 상태 저장 / 중복 방지 검증
- Telegram 실수신 테스트 성공
- Secret이 GitHub에 노출되지 않음
- 배포 후 README 업데이트
- 검증 완료 후에만 PR #1을 main에 merge

## 10. 사용자와의 작업 방식

사용자는 가급적 설정 절차를 직접 많이 하지 않고, Work가 가능한 작업은 직접 수행해주길 원한다.

따라서:

- 계정 인증/결제 승인/Telegram BotFather처럼 사용자 본인만 할 수 있는 단계만 짧게 요청
- 나머지는 GitHub 수정, 구성 파일 작성, 테스트, 배포, 로그 확인까지 최대한 직접 진행
- 각 단계에서 사용자가 해야 할 일을 한 번에 1~2개 정도로 최소화
- 작업 중 발견한 버그는 먼저 수정하고, 배포 성공 여부를 실제 로그/Telegram 수신으로 확인할 것
