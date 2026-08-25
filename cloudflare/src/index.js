import { calcSnapshot, deliverClaimedEvent, processMinute } from "./signal-engine.js";

const SYMBOL = "BTCUSDT";
const DELIVERY_LEASE_MS = 2 * 60 * 1000;
const MARKET_STREAM_URL = "https://data-stream.binance.vision/ws/btcusdt@kline_1d";

async function fetchCurrentDailyKlineStream() {
  const response = await fetch(MARKET_STREAM_URL, { headers: { Upgrade: "websocket" } });
  const socket = response.webSocket;
  if (!socket) throw new Error(`HTTP ${response.status}`);
  socket.accept();

  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      try { socket.close(1000, "timeout"); } catch {}
      reject(new Error("timeout"));
    }, 8000);
    const finish = (callback, value) => {
      clearTimeout(timeout);
      try { socket.close(1000, "done"); } catch {}
      callback(value);
    };
    socket.addEventListener("message", (event) => {
      try {
        const payload = JSON.parse(String(event.data));
        const kline = payload.k;
        if (!kline || kline.i !== "1d") return;
        finish(resolve, {
          openTime: Number(kline.t),
          close: Number(kline.c),
          closeTime: Number(kline.T),
        });
      } catch (error) {
        finish(reject, error);
      }
    });
    socket.addEventListener("error", () => finish(reject, new Error("websocket error")));
    socket.addEventListener("close", () => finish(reject, new Error("websocket closed")));
  });
}

async function updateAndReadStoredKlines(db, current) {
  const now = new Date().toISOString();
  await db.prepare(
    `INSERT INTO market_candles (open_time, close_time, close, updated_at)
     VALUES (?, ?, ?, ?)
     ON CONFLICT(open_time) DO UPDATE SET
       close_time = excluded.close_time,
       close = excluded.close,
       updated_at = excluded.updated_at`,
  ).bind(current.openTime, current.closeTime, current.close, now).run();
  const result = await db.prepare(
    `SELECT open_time, close_time, close
     FROM market_candles
     ORDER BY open_time DESC
     LIMIT 130`,
  ).all();
  return result.results.reverse().map((row) => ({
    openTime: Number(row.open_time),
    closeTime: Number(row.close_time),
    close: Number(row.close),
  }));
}

async function fetchDailyKlines(env) {
  const rows = await updateAndReadStoredKlines(env.DB, await fetchCurrentDailyKlineStream());
  if (rows.length < 120) throw new Error(`저장된 일봉 데이터가 120개보다 적습니다: ${rows.length}`);
  return { dataSource: "binance-global-market-stream", rows };
}

async function sendTelegram(env, text) {
  const response = await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      chat_id: env.TELEGRAM_CHAT_ID,
      text,
      disable_web_page_preview: true,
    }),
  });
  const body = await response.text();
  if (!response.ok) throw new Error(`Telegram HTTP ${response.status}: ${body.slice(0, 300)}`);
  const parsed = JSON.parse(body);
  if (!parsed.ok) throw new Error(`Telegram API 오류: ${body.slice(0, 300)}`);
}

async function readState(db) {
  const row = await db.prepare("SELECT state_json FROM alert_state WHERE id = 1").first();
  if (!row) return {};
  try {
    return JSON.parse(row.state_json);
  } catch (error) {
    throw new Error(`D1 state_json 파싱 실패: ${error.message}`);
  }
}

async function persistObservation(db, previousState, result) {
  if (result.duplicate) return false;
  const now = new Date().toISOString();
  const statements = [
    db.prepare(
      "INSERT INTO alert_state (id, state_json, updated_at) VALUES (1, ?1, ?2) " +
      "ON CONFLICT(id) DO UPDATE SET state_json = excluded.state_json, updated_at = excluded.updated_at",
    ).bind(JSON.stringify(result.state), now),
  ];
  for (const event of result.events) {
    statements.push(
      db.prepare(
        "INSERT OR IGNORE INTO alert_events " +
        "(id, type, text, status, attempts, created_at) VALUES (?1, ?2, ?3, 'pending', 0, ?4)",
      ).bind(event.id, event.type, event.text, now),
    );
  }
  await db.batch(statements);
  return previousState.lastProcessedMinute !== result.state.lastProcessedMinute;
}

async function claimEvent(db, event, leaseOwner, now) {
  const leaseUntil = now + DELIVERY_LEASE_MS;
  const result = await db.prepare(
    "UPDATE alert_events SET status = 'delivering', lease_owner = ?1, lease_until = ?2, " +
    "attempts = attempts + 1, last_attempt_at = ?3 " +
    "WHERE id = ?4 AND (status = 'pending' OR (status = 'delivering' AND COALESCE(lease_until, 0) <= ?5))",
  ).bind(leaseOwner, leaseUntil, new Date(now).toISOString(), event.id, now).run();
  return result.meta.changes === 1;
}

async function drainOutbox(env) {
  const now = Date.now();
  const leaseOwner = crypto.randomUUID();
  const result = await env.DB.prepare(
    "SELECT id, text FROM alert_events " +
    "WHERE status = 'pending' OR (status = 'delivering' AND COALESCE(lease_until, 0) <= ?1) " +
    "ORDER BY created_at LIMIT 20",
  ).bind(now).all();

  for (const event of result.results) {
    if (!await claimEvent(env.DB, event, leaseOwner, now)) continue;
    const delivery = await deliverClaimedEvent(event, {
      send: (text) => sendTelegram(env, text),
      markSent: async (id) => env.DB.prepare(
        "UPDATE alert_events SET status = 'sent', sent_at = ?1, lease_owner = NULL, " +
        "lease_until = NULL, last_error = NULL WHERE id = ?2 AND lease_owner = ?3",
      ).bind(new Date().toISOString(), id, leaseOwner).run(),
      markRetry: async (id, error) => env.DB.prepare(
        "UPDATE alert_events SET status = 'pending', lease_owner = NULL, lease_until = NULL, last_error = ?1 " +
        "WHERE id = ?2 AND lease_owner = ?3",
      ).bind(String(error?.message || error).slice(0, 500), id, leaseOwner).run(),
    });
    if (delivery === "retry") console.error(`Telegram 전송 재시도 예정: ${event.id}`);
  }
}

async function runMonitor(env, scheduledTime = Date.now()) {
  if (!env.TELEGRAM_BOT_TOKEN || !env.TELEGRAM_CHAT_ID) {
    throw new Error("TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHAT_ID Secret이 없습니다.");
  }
  const minuteKey = new Date(scheduledTime).toISOString().slice(0, 16);
  const market = await fetchDailyKlines(env);
  const live = calcSnapshot(market.rows, true, scheduledTime);
  const closed = calcSnapshot(market.rows, false, scheduledTime);
  live.dataSource = market.dataSource;
  closed.dataSource = market.dataSource;
  const previousState = await readState(env.DB);
  const result = processMinute(previousState, { live, closed, minuteKey });
  await persistObservation(env.DB, previousState, result);
  await drainOutbox(env);
  console.log(JSON.stringify({
    event: "btc_monitor_complete",
    minuteKey,
    duplicate: result.duplicate,
    eventsCreated: result.events.length,
    price: live.price,
    ma5: live.mas[5],
    ma20: live.mas[20],
    ma65: live.mas[65],
    ma120: live.mas[120],
    position: result.state.position,
    dataSource: market.dataSource,
  }));
}

export default {
  async scheduled(controller, env, context) {
    context.waitUntil(runMonitor(env, controller.scheduledTime));
  },
};

export {
  drainOutbox,
  fetchDailyKlines,
  persistObservation,
  readState,
  runMonitor,
};
