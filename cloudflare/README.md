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
- 현재가가 MA120을 위로 돌파하면 즉시 매수·보유 100% 알림
- 현재가가 MA120을 아래로 돌파하면 즉시 매도·미보유 0% 알림
- MA5 / MA20 / MA65는 메시지의 추세 참고값으로만 사용하고 매매 신호에는 사용하지 않음
- 마지막 확정 일봉 `closeTime`이 변경되면 실행 시각과 무관하게 종가 확정 알림을 한 번 전송
- 실시간 돌파 및 일봉 종가 알림에 MA120 대비 등락률을 `+/-0.00%` 형식으로 표시
- D1의 `alert_state`에 현재 비중과 신호 상태 저장
- D1의 `alert_events` outbox와 전송 lease로 중복 전송 방지 및 실패 재시도
- D1의 `market_candles`에 최근 Binance 일봉과 진행 중 일봉 저장

매매 판단은 현재가와 MA120의 관계만 사용합니다.

- 현재가 > MA120: 매수·보유 100%
- 현재가 < MA120: 매도·미보유 0%

## 검증

```bash
cd cloudflare
npm ci
npm run check
npm test
```

10개 테스트가 현재가 상향·하락 돌파, MA5·20·65 신호 제외, 기존 상태 전환, MA120 대비 등락률, 지연된 일봉 확정, 같은 분 중복 실행, Telegram 실패 재시도를 검증합니다.

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
