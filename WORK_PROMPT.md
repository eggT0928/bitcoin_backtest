# 유지보수용 작업 프롬프트

`WORK_HANDOFF.md`를 먼저 전체 확인하고 현재 배포된 Cloudflare Workers + D1 기반 BTC Telegram 알림을 이어서 유지보수한다.

- Repository: `eggT0928/bitcoin_backtest`
- Worker: `btc-telegram-alerts`
- D1: `btc-telegram-alerts`
- 운영 문서: `cloudflare/README.md`

Firebase 예약 함수는 비용 문제로 운영에 사용하지 않는다. 변경 시 `cloudflare` 테스트 전체를 실행하고, 실제 1분 Cron 로그와 D1 outbox를 확인한다. Telegram Token과 Chat ID는 Cloudflare Secrets로만 관리하며 채팅이나 저장소에 값을 노출하지 않는다. 자동 주문 기능은 추가하지 않는다.
