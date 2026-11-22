const SIGNAL_MAS = [5, 20, 65];
const ALL_MAS = [5, 20, 65, 120];
const STRATEGY_VERSION = "price-ma120-v1";

function sma(values, period) {
  if (values.length < period) return null;
  return values.slice(-period).reduce((sum, value) => sum + value, 0) / period;
}

function relationMap(mas) {
  return Object.fromEntries(SIGNAL_MAS.map((period) => [period, mas[period] > mas[120]]));
}

function calcSnapshot(rows, includeCurrent = true, now = Date.now()) {
  const selected = includeCurrent ? rows : rows.filter((row) => row.closeTime < now);
  if (selected.length < 120) throw new Error(`MA120 계산에 필요한 일봉이 부족합니다: ${selected.length}`);
  const closes = selected.map((row) => row.close);
  const latest = selected[selected.length - 1];
  const mas = Object.fromEntries(ALL_MAS.map((period) => [period, sma(closes, period)]));
  return {
    price: latest.close,
    mas,
    rel: relationMap(mas),
    candleOpenTime: latest.openTime,
    candleCloseTime: latest.closeTime,
  };
}

function isPriceAboveMa120(snapshot) {
  return snapshot.price > snapshot.mas[120];
}

function targetPosition(priceAboveMa120) {
  return priceAboveMa120 ? 1 : 0;
}

function distancePercent(price, reference) {
  return ((price / reference) - 1) * 100;
}

function fmtPercent(value) {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function fmt(value) {
  return value == null ? "-" : `$${Math.round(value).toLocaleString("en-US")}`;
}

function eventId(...parts) {
  return parts.join("-").replace(/[^a-zA-Z0-9_.:-]/g, "_");
}

function strategyStartedEvent(live) {
  const above = isPriceAboveMa120(live);
  const distance = distancePercent(live.price, live.mas[120]);
  return {
    id: "strategy-price-ma120-v1",
    type: "strategy-start",
    text:
      "✅ BTC 현재가/MA120 전략 적용\n" +
      "BTCUSDT / 1분 감시\n" +
      `현재가 ${fmt(live.price)} / MA120 ${fmt(live.mas[120])} (${fmtPercent(distance)})\n` +
      `현재 판단: ${above ? "매수·보유 (100%)" : "매도·미보유 (0%)"}\n` +
      "MA5·20·65는 추세 참고용으로 유지합니다.",
  };
}

function priceCrossEvent(direction, live, minuteKey) {
  const upward = direction === "up";
  const distance = distancePercent(live.price, live.mas[120]);
  return {
    id: eventId("price-ma120", direction, minuteKey),
    type: "price-ma120-cross",
    text:
      `${upward ? "🚀" : "🔻"} BTC 현재가 MA120 ${upward ? "상승돌파" : "하락돌파"}\n` +
      `현재가 ${fmt(live.price)} / MA120 ${fmt(live.mas[120])}\n` +
      `MA120 대비 ${fmtPercent(distance)}\n` +
      `매매 판단: ${upward ? "매수·보유 (100%)" : "매도·미보유 (0%)"}\n` +
      `추세 참고: MA5 ${fmt(live.mas[5])} · MA20 ${fmt(live.mas[20])} · MA65 ${fmt(live.mas[65])}\n` +
      "※ 1분 감시 중 포착된 장중 신호이며 일봉 종가 전에는 다시 바뀔 수 있습니다.",
  };
}

function kstDateFromClose(closeTime) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(closeTime + 1));
}

function dailyEvent(closed, previousAbove, position) {
  const above = isPriceAboveMa120(closed);
  const distance = distancePercent(closed.price, closed.mas[120]);
  const change = previousAbove === above
    ? "없음"
    : above ? "종가 기준 MA120 상승돌파" : "종가 기준 MA120 하락돌파";
  const order = ALL_MAS
    .map((period) => [`MA${period}`, closed.mas[period]])
    .sort((left, right) => right[1] - left[1])
    .map(([label]) => label)
    .join(" > ");
  const date = kstDateFromClose(closed.candleCloseTime);
  return {
    id: eventId("daily-close", closed.candleCloseTime),
    type: "daily-close",
    text:
      `🕘 BTC 일봉 종가 확정 (${date})\n` +
      `종가 ${fmt(closed.price)} / MA120 ${fmt(closed.mas[120])}\n` +
      `MA120 대비 ${fmtPercent(distance)}\n` +
      `종가 판단: ${above ? "MA120 위·매수 우위" : "MA120 아래·매도 우위"}\n` +
      `종가 변화: ${change}\n` +
      `추세 참고: MA5 ${fmt(closed.mas[5])} · MA20 ${fmt(closed.mas[20])} · MA65 ${fmt(closed.mas[65])}\n` +
      `이평선 배열: ${order}\n` +
      `현재 전략 비중: ${Math.round(position * 100)}%`,
  };
}

function liveFields(live) {
  return {
    price: live.price,
    ma5: live.mas[5],
    ma20: live.mas[20],
    ma65: live.mas[65],
    ma120: live.mas[120],
    priceAboveMa120: isPriceAboveMa120(live),
    candleCloseTime: live.candleCloseTime,
    dataSource: live.dataSource || "binance-global",
  };
}

function removeLegacyStrategyState(prior) {
  const { stableRelations, candidates, dailyRelations, ...current } = prior;
  return current;
}

function processMinute(previousState, { live, closed, minuteKey }) {
  const prior = previousState || {};
  const liveAbove = isPriceAboveMa120(live);
  const closedAbove = isPriceAboveMa120(closed);

  if (prior.strategyVersion !== STRATEGY_VERSION) {
    return {
      duplicate: false,
      events: [strategyStartedEvent(live)],
      state: {
        ...removeLegacyStrategyState(prior),
        initialized: true,
        strategyVersion: STRATEGY_VERSION,
        lastProcessedMinute: minuteKey,
        priceAboveMa120: liveAbove,
        position: targetPosition(liveAbove),
        live: liveFields(live),
        dailyPriceAboveMa120: closedAbove,
        lastClosedCandleCloseTime: prior.lastClosedCandleCloseTime ?? closed.candleCloseTime,
      },
    };
  }

  if (prior.lastProcessedMinute === minuteKey) {
    return { state: prior, events: [], duplicate: true };
  }

  const events = [];
  if (Boolean(prior.priceAboveMa120) !== liveAbove) {
    events.push(priceCrossEvent(liveAbove ? "up" : "down", live, minuteKey));
  }

  const position = targetPosition(liveAbove);
  const state = {
    ...prior,
    initialized: true,
    strategyVersion: STRATEGY_VERSION,
    lastProcessedMinute: minuteKey,
    priceAboveMa120: liveAbove,
    position,
    live: liveFields(live),
  };

  if (closed.candleCloseTime !== prior.lastClosedCandleCloseTime) {
    events.push(dailyEvent(closed, Boolean(prior.dailyPriceAboveMa120), position));
    state.dailyPriceAboveMa120 = closedAbove;
    state.lastClosedCandleCloseTime = closed.candleCloseTime;
  }

  return { state, events, duplicate: false };
}

async function deliverClaimedEvent(event, { send, markSent, markRetry }) {
  try {
    await send(event.text);
    await markSent(event.id);
    return "sent";
  } catch (error) {
    await markRetry(event.id, error);
    return "retry";
  }
}

export {
  ALL_MAS,
  SIGNAL_MAS,
  STRATEGY_VERSION,
  calcSnapshot,
  deliverClaimedEvent,
  distancePercent,
  isPriceAboveMa120,
  processMinute,
  relationMap,
  sma,
  targetPosition,
};
