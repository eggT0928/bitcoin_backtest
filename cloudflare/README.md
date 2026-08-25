# BTC 1분 추세신호 Telegram 알림

Cloudflare Workers Cron + D1 + Binance 공개 시세 스트림 + Telegram Bot으로 동작합니다. 자동 주문 기능은 없습니다.

## 운영 배포

- Worker: `btc-telegram-alerts`
- URL: `https://btc-telegram-alerts.btc-telegram-alerts-worker.workers.dev`
- Cron: 매 1분 (`* * * * *`)
- D1: `btc-telegram-alerts` (`8ece5f02-d4bd-4476-a31a-8cb80aec593b`)
- Telegram Bot: `@BTC_checker_bot`
- 시세: Binance 글로벌 공개 `BTCUSDT` 1일봉 스트림
- Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

Cloudflare Workers/D1 및 Telegram의 무료 한도 안에서 동작하도록 구성했으며 Binance API Key는 사용하지 않습니다.

## 동작

- MA5 / MA20 / MA65 / MA120을 1분마다 계산
- 교차 순간 장중 미확정 알림을 한 번 전송
- 같은 방향으로 3회 연속 관측되면 3분 유지 확인 알림을 한 번 전송
- 마지막 확정 일봉 `closeTime`이 변경되면 실행 시각과 무관하게 종가 확정 알림을 한 번 전송
- D1의 `alert_state`에 현재 비중과 신호 상태 저장
- D1의 `alert_events` outbox와 전송 lease로 중복 전송 방지 및 실패 재시도
- D1의 `market_candles`에 최근 Binance 일봉과 진행 중 일봉 저장

비중은 현재 MA 배열을 매번 정적으로 환산하지 않고 교차 이벤트로 전이합니다.

- 상향: MA5 50%, MA20 75%, MA65 100%까지 `max`
- 하향: MA5 최대 50%, MA20 최대 25%, MA65 0%까지 `min`

## 검증

```bash
cd cloudflare
npm ci
npm run check
npm test
```

11개 테스트가 신호 없음, 즉시 교차, 원복, 3분 유지, 비중 전이, 지연된 일봉 확정, 같은 분 중복 실행, Telegram 실패 재시도를 검증합니다.

## 새 환경에 배포할 때

```bash
cd cloudflare
npm ci
npx wrangler d1 migrations apply btc-telegram-alerts --remote
npm run seed:sql > seed.sql
npx wrangler d1 execute btc-telegram-alerts --remote --file seed.sql
npx wrangler secret put TELEGRAM_BOT_TOKEN
npx wrangler secret put TELEGRAM_CHAT_ID
npm run deploy
```

토큰과 Chat ID는 입력 프롬프트에서만 입력하고 소스나 `.env`에 저장하지 않습니다. `seed.sql`은 `.gitignore` 대상입니다.

## 운영 확인

```bash
npm run tail
npx wrangler d1 execute btc-telegram-alerts --remote --command "SELECT id,type,status,attempts,sent_at,last_error FROM alert_events ORDER BY created_at DESC LIMIT 10;"
```

장중 알림은 일봉 마감 전에 취소될 수 있으므로 종가 확정 알림과 구분해 사용해야 합니다.
