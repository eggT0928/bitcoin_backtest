"use strict";

const SIGNAL_MAS = [5, 20, 65];
const ALL_MAS = [5, 20, 65, 120];
const BUY_TARGETS = { 5: 0.5, 20: 0.75, 65: 1.0 };
const SELL_LIMITS = { 5: 0.5, 20: 0.25, 65: 0.0 };

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

function initialPosition(relations) {
  return SIGNAL_MAS.reduce(
    (position, period) => relations[period] ? Math.max(position, BUY_TARGETS[period]) : position,
    0,
  );
}

// app.py calculate_event_position(..., sell_mode="partial")와 같은 우선순위다.
function applyPositionEvents(currentPosition, crossings) {
  let position = Number.isFinite(currentPosition) ? currentPosition : 0;
  const down = new Set(crossings.filter((crossing) => !crossing.direction).map((crossing) => crossing.period));
  const up = new Set(crossings.filter((crossing) => crossing.direction).map((crossing) => crossing.period));
  let majorRiskOff = false;

  if (down.has(65)) {
    position = SELL_LIMITS[65];
    majorRiskOff = true;
  } else if (down.has(20)) {
    position = Math.min(position, SELL_LIMITS[20]);
  } else if (down.has(5)) {
    position = Math.min(position, SELL_LIMITS[5]);
  }

  if (!majorRiskOff) {
    for (const period of SIGNAL_MAS) {
      if (up.has(period)) position = Math.max(position, BUY_TARGETS[period]);
    }
  }
  return position;
}

function fmt(value) {
  return value == null ? "-" : `$${Math.round(value).toLocaleString("en-US")}`;
}

function eventId(...parts) {
  return parts.join("-").replace(/[^a-zA-Z0-9_.:-]/g, "_");
}

function startupEvent(live) {
  return {
    id: "monitor-started-v1",
    type: "startup",
    text:
      "✅ BTC 추세 모니터링 시작\n" +
      "BTCUSDT / 1분 감시\n" +
      "MA5·20·65 vs MA120\n" +
      `Firebase 연결 정상 · 현재가 ${fmt(live.price)}`,
  };
}

function immediateEvent(period, direction, candidate, live) {
  return {
    id: eventId("immediate", period, direction ? "up" : "down", candidate.startedMinute),
    type: "intraday-immediate",
    text:
      "⚡ BTC 장중 교차 포착 (미확정)\n" +
      `BTCUSDT ${fmt(live.price)}\n` +
      `MA${period} ${fmt(live.mas[period])} ${direction ? ">" : "<"} MA120 ${fmt(live.mas[120])}\n` +
      `${direction ? "상향돌파" : "하향돌파"} 감지 · 1분차\n` +
      "3분 유지 여부를 계속 확인합니다.",
  };
}

function confirmedEvent(crossing, before, after, live) {
  return {
    id: eventId("confirmed", crossing.period, crossing.direction ? "up" : "down", crossing.startedMinute),
    type: "intraday-confirmed",
    text:
      "✅ BTC 교차 3분 유지 확인\n" +
      `MA${crossing.period} ${crossing.direction ? "↑" : "↓"} MA120\n` +
      `BTCUSDT ${fmt(live.price)}\n` +
      `MA${crossing.period} ${fmt(live.mas[crossing.period])} / MA120 ${fmt(live.mas[120])}\n` +
      `전략 참고 비중: ${Math.round(before * 100)}% → ${Math.round(after * 100)}%\n` +
      "※ 장중 신호이며 일봉 종가 확정 전입니다.",
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

function dailyEvent(closed, previousRelations, position) {
  const changes = SIGNAL_MAS.flatMap((period) =>
    Boolean(previousRelations[period]) === Boolean(closed.rel[period])
      ? []
      : [`MA${period} ${closed.rel[period] ? "↑" : "↓"} MA120`],
  );
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
      `종가 ${fmt(closed.price)}\n` +
      `MA5 ${fmt(closed.mas[5])}\nMA20 ${fmt(closed.mas[20])}\nMA65 ${fmt(closed.mas[65])}\nMA120 ${fmt(closed.mas[120])}\n` +
      `배열: ${order}\n` +
      `확정 변화: ${changes.length ? changes.join(", ") : "없음"}\n` +
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
    candleCloseTime: live.candleCloseTime,
  };
}

function processMinute(previousState, { live, closed, minuteKey }) {
  const prior = previousState || {};
  if (prior.lastProcessedMinute === minuteKey) {
    return { state: prior, events: [], duplicate: true };
  }

  const hasBaseline = prior.initialized === true || prior.stableRelations != null;
  if (!hasBaseline) {
    return {
      duplicate: false,
      events: [startupEvent(live)],
      state: {
        ...prior,
        initialized: true,
        lastProcessedMinute: minuteKey,
        stableRelations: { ...live.rel },
        candidates: {},
        position: initialPosition(live.rel),
        live: liveFields(live),
        dailyRelations: { ...closed.rel },
        lastClosedCandleCloseTime: closed.candleCloseTime,
      },
    };
  }

  const stable = { ...prior.stableRelations };
  const candidates = { ...(prior.candidates || {}) };
  const events = [];
  const confirmedCrossings = [];

  for (const period of SIGNAL_MAS) {
    const observed = Boolean(live.rel[period]);
    const stableValue = Boolean(stable[period]);
    if (observed === stableValue) {
      delete candidates[period];
      continue;
    }

    const oldCandidate = candidates[period];
    const candidate = oldCandidate && Boolean(oldCandidate.direction) === observed
      ? { ...oldCandidate, streak: Number(oldCandidate.streak || 0) + 1, lastMinute: minuteKey }
      : { direction: observed, streak: 1, startedMinute: minuteKey, lastMinute: minuteKey, immediateEmitted: false };

    if (!candidate.immediateEmitted) {
      events.push(immediateEvent(period, observed, candidate, live));
      candidate.immediateEmitted = true;
    }

    if (candidate.streak >= 3) {
      stable[period] = observed;
      confirmedCrossings.push({ period, direction: observed, startedMinute: candidate.startedMinute });
      delete candidates[period];
    } else {
      candidates[period] = candidate;
    }
  }

  const beforePosition = Number.isFinite(prior.position)
    ? prior.position
    : initialPosition(prior.stableRelations);
  const afterPosition = applyPositionEvents(beforePosition, confirmedCrossings);
  for (const crossing of confirmedCrossings) {
    events.push(confirmedEvent(crossing, beforePosition, afterPosition, live));
  }

  const state = {
    ...prior,
    initialized: true,
    lastProcessedMinute: minuteKey,
    stableRelations: stable,
    candidates,
    position: afterPosition,
    live: liveFields(live),
  };

  if (closed.candleCloseTime !== prior.lastClosedCandleCloseTime) {
    events.push(dailyEvent(closed, prior.dailyRelations || closed.rel, afterPosition));
    state.dailyRelations = { ...closed.rel };
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

module.exports = {
  ALL_MAS,
  BUY_TARGETS,
  SELL_LIMITS,
  SIGNAL_MAS,
  applyPositionEvents,
  calcSnapshot,
  deliverClaimedEvent,
  initialPosition,
  processMinute,
  relationMap,
  sma,
};
