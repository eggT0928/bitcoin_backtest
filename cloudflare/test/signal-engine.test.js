import test from "node:test";
import assert from "node:assert/strict";
import {
  STRATEGY_VERSION,
  calcSnapshot,
  deliverClaimedEvent,
  distancePercent,
  processMinute,
} from "../src/signal-engine.js";

const MINUTES = ["2026-11-22T00:00", "2026-11-22T00:01", "2026-11-22T00:02"];

function snapshot({ price = 99, ma120 = 100, ma5 = 98, ma20 = 97, ma65 = 96, closeTime = 1_000 } = {}) {
  const mas = { 5: ma5, 20: ma20, 65: ma65, 120: ma120 };
  return {
    price,
    mas,
    rel: { 5: ma5 > ma120, 20: ma20 > ma120, 65: ma65 > ma120 },
    candleOpenTime: closeTime - 100,
    candleCloseTime: closeTime,
  };
}

function baseline(priceAboveMa120 = false) {
  return {
    initialized: true,
    strategyVersion: STRATEGY_VERSION,
    priceAboveMa120,
    position: priceAboveMa120 ? 1 : 0,
    dailyPriceAboveMa120: false,
    lastClosedCandleCloseTime: 1_000,
  };
}

function run(state, live, minuteIndex = 0, closed = snapshot()) {
  return processMinute(state, { live, closed, minuteKey: MINUTES[minuteIndex] });
}

test("변화가 없으면 Telegram 이벤트가 없다", () => {
  const result = run(baseline(false), snapshot({ price: 99, ma120: 100 }));
  assert.deepEqual(result.events, []);
  assert.equal(result.state.position, 0);
});

test("현재가가 MA120을 상승돌파하면 즉시 매수 100% 알림을 한 번 생성한다", () => {
  let result = run(baseline(false), snapshot({ price: 101, ma120: 100 }), 0);
  assert.deepEqual(result.events.map((event) => event.type), ["price-ma120-cross"]);
  assert.match(result.events[0].text, /상승돌파/);
  assert.match(result.events[0].text, /매수·보유 \(100%\)/);
  assert.match(result.events[0].text, /MA120 대비 \+1\.00%/);
  assert.equal(result.state.position, 1);

  result = run(result.state, snapshot({ price: 102, ma120: 100 }), 1);
  assert.deepEqual(result.events, []);
});

test("현재가가 MA120을 하락돌파하면 즉시 매도 0% 알림을 한 번 생성한다", () => {
  const result = run(baseline(true), snapshot({ price: 99, ma120: 100 }));
  assert.deepEqual(result.events.map((event) => event.type), ["price-ma120-cross"]);
  assert.match(result.events[0].text, /하락돌파/);
  assert.match(result.events[0].text, /매도·미보유 \(0%\)/);
  assert.match(result.events[0].text, /MA120 대비 -1\.00%/);
  assert.equal(result.state.position, 0);
});

test("MA5·20·65가 MA120을 교차해도 현재가 관계가 같으면 매매 알림이 없다", () => {
  const result = run(
    baseline(true),
    snapshot({ price: 110, ma120: 100, ma5: 101, ma20: 102, ma65: 103 }),
  );
  assert.deepEqual(result.events, []);
  assert.equal(result.state.position, 1);
});

test("같은 분 중복 실행은 돌파 알림과 상태를 중복 처리하지 않는다", () => {
  const first = run(baseline(false), snapshot({ price: 101, ma120: 100 }), 0);
  const duplicate = run(first.state, snapshot({ price: 101, ma120: 100 }), 0);
  assert.equal(duplicate.duplicate, true);
  assert.deepEqual(duplicate.events, []);
  assert.equal(duplicate.state.position, 1);
});

test("기존 MA 교차 전략 상태는 현재가/MA120 기준으로 한 번만 안전하게 전환한다", () => {
  const oldState = {
    initialized: true,
    stableRelations: { 5: true, 20: false, 65: false },
    candidates: { 5: { streak: 2 } },
    dailyRelations: { 5: true, 20: false, 65: false },
    position: 0.5,
    lastClosedCandleCloseTime: 1_000,
  };
  const migrated = run(oldState, snapshot({ price: 101, ma120: 100 }));
  assert.deepEqual(migrated.events.map((event) => event.type), ["strategy-start"]);
  assert.equal(migrated.state.strategyVersion, STRATEGY_VERSION);
  assert.equal(migrated.state.priceAboveMa120, true);
  assert.equal(migrated.state.position, 1);
  assert.equal(migrated.state.stableRelations, undefined);
  assert.equal(migrated.state.candidates, undefined);

  const next = run(migrated.state, snapshot({ price: 101, ma120: 100 }), 1);
  assert.deepEqual(next.events, []);
});

test("09:01~09:02 지연 실행에도 종가 알림은 한 번이며 MA120 대비 등락률을 표시한다", () => {
  const delayed = run(
    baseline(false),
    snapshot({ price: 101, ma120: 100 }),
    1,
    snapshot({ price: 98, ma120: 100, closeTime: 2_000 }),
  );
  assert.deepEqual(delayed.events.map((event) => event.type), ["price-ma120-cross", "daily-close"]);
  assert.match(delayed.events[1].text, /MA120 대비 -2\.00%/);

  const next = run(
    delayed.state,
    snapshot({ price: 101, ma120: 100 }),
    2,
    snapshot({ price: 98, ma120: 100, closeTime: 2_000 }),
  );
  assert.deepEqual(next.events, []);
});

test("MA120 대비 등락률을 정확히 계산한다", () => {
  assert.ok(Math.abs(distancePercent(101, 100) - 1) < 1e-10);
  assert.ok(Math.abs(distancePercent(98, 100) + 2) < 1e-10);
});

test("Telegram 실패 시 sent 처리하지 않고 재시도 상태로 되돌린다", async () => {
  let markedSent = false;
  let retryError;
  const status = await deliverClaimedEvent({ id: "event-1", text: "test" }, {
    send: async () => { throw new Error("Telegram 500"); },
    markSent: async () => { markedSent = true; },
    markRetry: async (_id, error) => { retryError = error; },
  });
  assert.equal(status, "retry");
  assert.equal(markedSent, false);
  assert.match(retryError.message, /Telegram 500/);
});

test("Binance 형식 데이터에서 MA와 진행/확정 일봉을 정확히 구분한다", () => {
  const rows = Array.from({ length: 121 }, (_, index) => ({
    openTime: index * 1_000,
    close: index + 1,
    closeTime: index * 1_000 + 999,
  }));
  const live = calcSnapshot(rows, true, 120_500);
  const closed = calcSnapshot(rows, false, 120_500);
  assert.equal(live.mas[5], 119);
  assert.equal(live.mas[120], 61.5);
  assert.equal(closed.price, 120);
  assert.equal(closed.candleCloseTime, 119_999);
});
