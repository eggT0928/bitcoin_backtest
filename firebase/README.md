# BTC 1분 추세신호 Telegram 알림

Firebase Cloud Functions 2nd gen + Cloud Scheduler + Firestore + Binance BTCUSDT + Telegram Bot 조합입니다.

## 동작

- 1분마다 BTCUSDT 일봉 데이터를 Binance에서 조회
- MA5 / MA20 / MA65 / MA120 실시간 계산
- MA5·20·65와 MA120의 상향/하향 교차를 1분 단위로 감지
- 최초 교차 시 Telegram에 `장중 교차 포착(미확정)` 즉시 알림
- 같은 방향으로 3회 연속(약 3분) 유지되면 `3분 유지 확인` 알림
- 매일 한국시간 09:00에 직전 확정 일봉 기준 MA와 배열, 확정 교차 변화를 Telegram으로 재알림
- Firestore `btcAlerts/state`에 상태를 저장해 같은 신호의 중복 알림을 억제

전략 참고 비중은 기존 앱 규칙을 사용합니다.

- MA5 > MA120: 50%
- MA20 > MA120: 75%
- MA65 > MA120: 100%

## 1. 준비

Firebase 프로젝트에서 다음을 준비합니다.

1. Blaze 요금제 활성화
2. Firestore Database 생성
3. Firebase CLI 설치 및 로그인
4. Telegram에서 @BotFather로 봇 생성
5. 생성한 봇과 개인 채팅에서 `/start` 한 번 전송
6. Bot Token과 Chat ID 확보

## 2. Firebase 프로젝트 연결

저장소 루트에서:

```bash
firebase login
firebase use --add
```

원하는 Firebase 프로젝트를 선택합니다.

## 3. Telegram Secret 등록

```bash
firebase functions:secrets:set TELEGRAM_BOT_TOKEN
firebase functions:secrets:set TELEGRAM_CHAT_ID
```

각 명령이 값을 물으면 BotFather 토큰과 개인 Chat ID를 입력합니다.

> 토큰과 Chat ID를 GitHub 소스코드나 `.env`에 커밋하지 마세요.

## 4. 의존성 설치 및 문법 검사

```bash
cd firebase/functions
npm install
npm run lint
cd ../..
```

## 5. 배포

```bash
firebase deploy --only functions:checkBtcMaSignals
```

배포 후 Google Cloud Scheduler에 1분 주기의 예약 작업이 자동 생성됩니다.

## 6. Firestore 상태

문서 경로:

```text
btcAlerts/state
```

주요 필드:

- `stableRelations`: 3분 유지 확인된 MA5/20/65 vs MA120 상태
- `candidates`: 아직 3분 확인 중인 교차 후보
- `immediateSent`: 장중 최초 교차 중복방지
- `live`: 가장 최근 가격과 MA 값
- `dailyRelations`: 직전 09:00 확정 일봉 상태
- `lastDailySummaryDate`: 일봉 확정 알림 중복방지

## 주의

이 알림은 투자 주문을 자동 실행하지 않습니다. 장중 신호는 일봉 마감 전에 다시 취소될 수 있으므로, 09:00 확정 일봉 알림과 구분해 사용하세요.
