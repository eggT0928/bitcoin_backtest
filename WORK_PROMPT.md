# ChatGPT Work 이어서 작업 프롬프트

아래 내용을 Work 새 작업에 그대로 사용하세요.

---

현재 진행 중인 BTC 추세추종 알림 프로젝트를 이어서 완성해줘.

## 반드시 먼저 확인할 것

GitHub 연결을 사용해서 아래 저장소와 작업물을 직접 읽어.

- Repository: `eggT0928/bitcoin_backtest`
- Base branch: `main`
- 작업 branch: `feature/firebase-btc-telegram-alerts`
- Pull Request: `#1 Add Firebase 1-minute BTC Telegram signal alerts`
- 인수인계 문서: `WORK_HANDOFF.md`

특히 `WORK_HANDOFF.md`를 가장 먼저 읽고, 현재까지 구현된 코드와 남은 문제를 확인한 다음 이어서 작업해. 처음부터 새로 만들지 말고 기존 branch/PR을 계속 사용해.

## 최종 목표

Firebase 기반으로 BTCUSDT를 1분마다 감시하고 Telegram으로 추세 신호를 보내는 시스템을 실제 배포까지 완료해.

필수 기능:

1. Binance `BTCUSDT` 일봉 데이터 사용
2. MA5 / MA20 / MA65 / MA120 계산
3. MA5·20·65와 MA120의 상향/하향 교차를 1분 단위로 감지
4. 최초 교차 순간 Telegram에 장중 미확정 알림
5. 같은 방향 3분 연속 유지 시 확인 알림
6. 새 일봉이 확정되면 종가 기준 확정 알림
7. Firestore에 상태 저장 및 중복 알림 방지
8. Telegram Secret은 Firebase Secret Manager 사용
9. 자동 주문은 하지 말고 신호 알림만 제공

## 전략 비중 규칙

상향 교차:

- MA5 ↑ MA120 → 50%
- MA20 ↑ MA120 → 75%
- MA65 ↑ MA120 → 100%

하향 교차:

- MA5 ↓ MA120 → 최대 50%
- MA20 ↓ MA120 → 최대 25%
- MA65 ↓ MA120 → 0%

이 전략은 이벤트 기반 상태 전이이므로 현재 MA 관계만 보고 정적으로 비중을 계산하면 안 돼. 기존 `app.py`의 이벤트 전략과 같은 결과가 나오도록 구현하고 테스트해.

## 배포 전 반드시 해결할 두 가지

1. 현재 Firebase 코드의 `targetPosition(rel)`은 하향 교차 시 기존 부분매도 전략과 불일치할 수 있으므로 Firestore에 실제 `position` 상태를 저장하고 교차 이벤트로 갱신하도록 수정해.
2. 일봉 확정 알림을 KST 09:00 정확한 1분에만 의존하지 말고, 마지막 확정 캔들의 `closeTime`/ID 변화를 감지해서 Scheduler가 09:01~09:02에 실행돼도 놓치지 않도록 수정해.

자세한 내용은 `WORK_HANDOFF.md`를 기준으로 해.

## Firebase / Google Cloud 작업 방식

가능한 작업은 네가 직접 수행해. Firebase/Google Cloud 프로젝트 생성, 설정, CLI, 배포 등을 Work 환경에서 인증된 계정으로 직접 처리할 수 있다면 직접 진행해.

사용자 본인만 해야 하는 계정 인증, 결제 승인, Telegram BotFather 조작 같은 단계가 나오면 그때만 사용자에게 최소한의 행동을 요청해. 한 번에 너무 많은 수동 절차를 주지 말고, 1~2단계씩 안내한 뒤 다시 직접 이어서 진행해.

## 보안

- Telegram Bot Token을 채팅에 붙여넣으라고 요청하지 마.
- Bot Token을 GitHub에 커밋하지 마.
- Secret Manager/Firebase Functions secrets에 저장해.
- 다른 API key/credential도 source에 넣지 마.

## 테스트 및 완료 조건

코드 작성만 하고 끝내지 말고 실제 운영 가능한지 확인해.

- npm install / 문법검사 / 필요한 테스트 수행
- MA 계산 정확성 확인
- 상향·하향 비중 전이 테스트
- 1분 중복 invocation 방지 테스트
- 3분 유지 로직 테스트
- 일봉 확정 감지 테스트
- Firebase Functions 실제 배포
- Cloud Scheduler 1분 작업 확인
- Firestore 상태 생성 확인
- Functions 로그 확인
- Telegram 실제 수신 테스트

테스트를 위해 실제 시장 교차를 기다리지 말고 신호 계산을 순수 함수로 분리해 테스트 입력으로 검증해.

모든 것이 실제로 동작한 것을 확인한 후 README를 최신화하고, 그다음에만 PR #1을 main에 merge해.

작업 중에는 현재 상태와 다음 행동을 짧게 알려주고, 가능한 작업은 질문만 하지 말고 직접 진행해.

---
