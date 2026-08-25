"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { applyPositionEvents, calcSnapshot, deliverClaimedEvent, processMinute } = require("../signal-engine");

const MINUTES = ["2026-08-25T00:00", "2026-08-25T00:01", "2026-08-25T00:02", "2026-08-25T00:03"];

function snapshot(rel = { 5: false, 20: false, 65: false }, closeTime = 1_000) {
  return {
    price: 100,
    mas: { 5: rel[5] ? 101 : 99, 20: rel[20] ? 101 : 99, 65: rel[65] ? 101 : 99, 120: 100 },
    rel: { ...rel },
    candleOpenTime: closeTime - 100,
    candleCloseTime: closeTime,
  };
}

function baseline(position = 0, rel = { 5: false, 20: false, 65: false }) {
  return {
    initialized: true,
    stableRelations: { ...rel },
    candidates: {},
    position,
    dailyRelations: { ...rel },
    lastClosedCandleCloseTime: 1_000,
  };
}

function run(state, rel, minuteIndex, closed = snapshot(undefined, 1_000)) {
  return processMinute(state, { live: snapshot(rel), closed, minuteKey: MINUTES[minuteIndex] });
}

test("1. 관계 변화가 없으면 Telegram 이벤트가 없다", () => {
  assert.deepEqual(run(baseline(), { 5: false, 20: false, 65: false }, 0).events, []);
});

test("2, 5. MA5 아래→위 즉시 1회, 같은 상태에서는 중복 없음", () => {
  let result = run(baseline(), { 5: true, 20: false, 65: false }, 0);
  assert.deepEqual(result.events.map((event) => event.type), ["intraday-immediate"]);
  result = run(result.state, { 5: true, 20: false, 65: false }, 1);
  assert.deepEqual(result.events, []);
});

test("3. 교차 직후 원복하면 3분 유지 알림이 없다", () => {
  const first = run(baseline(), { 5: true, 20: false, 65: false }, 0);
  const reverted = run(first.state, { 5: false, 20: false, 65: false }, 1);
  assert.deepEqual(reverted.events, []);
  assert.equal(reverted.state.candidates[5], undefined);
});

test("4, 5. 3회 연속 유지 시 확인 알림 1회 후 추가 중복 없음", () => {
  let result = run(baseline(), { 5: true, 20: false, 65: false }, 0);
  result = run(result.state, { 5: true, 20: false, 65: false }, 1);
  result = run(result.state, { 5: true, 20: false, 65: false }, 2);
  assert.deepEqual(result.events.map((event) => event.type), ["intraday-confirmed"]);
  assert.equal(result.state.position, 0.5);
  result = run(result.state, { 5: true, 20: false, 65: false }, 3);
  assert.deepEqual(result.events, []);
});

test("6~10. app.py 이벤트 기반 부분매도 비중 전이와 일치한다", () => {
  let position = 0;
  position = applyPositionEvents(position, [{ period: 5, direction: true }]);
  assert.equal(position, 0.5);
  position = applyPositionEvents(position, [{ period: 20, direction: true }]);
  assert.equal(position, 0.75);
  position = applyPositionEvents(position, [{ period: 65, direction: true }]);
  assert.equal(position, 1);
  position = applyPositionEvents(position, [{ period: 5, direction: false }]);
  assert.equal(position, 0.5);
  position = applyPositionEvents(position, [{ period: 20, direction: false }]);
  assert.equal(position, 0.25);
  position = applyPositionEvents(position, [{ period: 65, direction: false }]);
  assert.equal(position, 0);
});

test("app.py처럼 MA65 하향일에는 같은 관측의 상향 신호를 무시한다", () => {
  assert.equal(applyPositionEvents(1, [
    { period: 65, direction: false },
    { period: 5, direction: true },
  ]), 0);
});

test("11. 09:01~09:02 실행이어도 closeTime 변화로 일봉 알림은 한 번만 생성된다", () => {
  const delayed = processMinute(baseline(), {
    live: snapshot(), closed: snapshot(undefined, 2_000), minuteKey: "2026-08-25T00:02",
  });
  assert.deepEqual(delayed.events.map((event) => event.type), ["daily-close"]);
  const next = processMinute(delayed.state, {
    live: snapshot(), closed: snapshot(undefined, 2_000), minuteKey: "2026-08-25T00:03",
  });
  assert.deepEqual(next.events, []);
});

test("12. 같은 분 중복 실행은 후보 streak와 이벤트를 중복 처리하지 않는다", () => {
  const first = run(baseline(), { 5: true, 20: false, 65: false }, 0);
  const duplicate = run(first.state, { 5: true, 20: false, 65: false }, 0);
  assert.equal(duplicate.duplicate, true);
  assert.equal(duplicate.state.candidates[5].streak, 1);
  assert.deepEqual(duplicate.events, []);
});

test("13. Telegram 실패 시 sent 처리하지 않고 재시도 상태로 되돌린다", async () => {
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
