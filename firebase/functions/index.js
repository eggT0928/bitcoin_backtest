const { onSchedule } = require("firebase-functions/v2/scheduler");
const { defineSecret } = require("firebase-functions/params");
const { initializeApp } = require("firebase-admin/app");
const { getFirestore, FieldValue } = require("firebase-admin/firestore");

initializeApp();
const db = getFirestore();

const TELEGRAM_BOT_TOKEN = defineSecret("TELEGRAM_BOT_TOKEN");
const TELEGRAM_CHAT_ID = defineSecret("TELEGRAM_CHAT_ID");

const SYMBOL = "BTCUSDT";
const SIGNAL_MAS = [5, 20, 65];
const BASE_MA = 120;
const TARGETS = { 5: 0.5, 20: 0.75, 65: 1.0 };
const STATE_REF = db.collection("btcAlerts").doc("state");

function sma(values, n) {
  if (values.length < n) return null;
  const slice = values.slice(-n);
  return slice.reduce((a, b) => a + b, 0) / n;
}

function relationMap(mas) {
  return {
    5: mas[5] > mas[120],
    20: mas[20] > mas[120],
    65: mas[65] > mas[120],
  };
}

function targetPosition(rel) {
  let target = 0;
  for (const n of SIGNAL_MAS) {
    if (rel[n]) target = Math.max(target, TARGETS[n]);
  }
  return target;
}

function fmt(x) {
  return x == null ? "-" : `$${Math.round(x).toLocaleString("en-US")}`;
}

async function fetchDailyKlines() {
  const url = `https://api.binance.com/api/v3/klines?symbol=${SYMBOL}&interval=1d&limit=130`;
  const res = await fetch(url, { headers: { "User-Agent": "btc-ma-alert/1.0" } });
  if (!res.ok) throw new Error(`Binance HTTP ${res.status}`);
  const rows = await res.json();
  return rows.map((r) => ({
    openTime: Number(r[0]),
    close: Number(r[4]),
    closeTime: Number(r[6]),
  }));
}

function calcSnapshot(rows, includeCurrent = true) {
  const now = Date.now();
  let use = rows;
  if (!includeCurrent) use = rows.filter((r) => r.closeTime < now);
  const closes = use.map((r) => r.close);
  const latest = use[use.length - 1];
  const mas = {};
  for (const n of [5, 20, 65, 120]) mas[n] = sma(closes, n);
  return { price: latest.close, mas, rel: relationMap(mas), candleCloseTime: latest.closeTime };
}

async function sendTelegram(text) {
  const token = TELEGRAM_BOT_TOKEN.value();
  const chatId = TELEGRAM_CHAT_ID.value();
  const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text, disable_web_page_preview: true }),
  });
  if (!res.ok) throw new Error(`Telegram HTTP ${res.status}: ${await res.text()}`);
}

function kstParts(date = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(date).reduce((o, p) => ({ ...o, [p.type]: p.value }), {});
  return { date: `${parts.year}-${parts.month}-${parts.day}`, hour: Number(parts.hour), minute: Number(parts.minute) };
}

exports.checkBtcMaSignals = onSchedule(
  {
    schedule: "* * * * *",
    timeZone: "Asia/Seoul",
    region: "asia-northeast3",
    timeoutSeconds: 30,
    memory: "256MiB",
    secrets: [TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID],
  },
  async () => {
    const minuteKey = new Date().toISOString().slice(0, 16);
    const claimed = await db.runTransaction(async (tx) => {
      const snap = await tx.get(STATE_REF);
      const data = snap.exists ? snap.data() : {};
      if (data.lastProcessedMinute === minuteKey) return false;
      tx.set(STATE_REF, { lastProcessedMinute: minuteKey, updatedAt: FieldValue.serverTimestamp() }, { merge: true });
      return true;
    });
    if (!claimed) return;

    const rows = await fetchDailyKlines();
    const live = calcSnapshot(rows, true);
    const closed = calcSnapshot(rows, false);
    const kst = kstParts();

    const snap = await STATE_REF.get();
    const state = snap.exists ? snap.data() : {};
    const stable = state.stableRelations || live.rel;
    const candidates = state.candidates || {};
    const immediateSent = state.immediateSent || {};
    const nextCandidates = { ...candidates };
    const nextImmediateSent = { ...immediateSent };
    const alerts = [];
    const confirmedAlerts = [];
    const nextStable = { ...stable };

    for (const n of SIGNAL_MAS) {
      const observed = live.rel[n];
      const stableValue = Boolean(stable[n]);
      if (observed === stableValue) {
        delete nextCandidates[n];
        delete nextImmediateSent[n];
        continue;
      }

      const prior = candidates[n];
      if (prior && prior.direction === observed) {
        nextCandidates[n] = { ...prior, streak: Number(prior.streak || 0) + 1 };
      } else {
        nextCandidates[n] = { direction: observed, streak: 1, startedAt: new Date().toISOString() };
      }

      const directionKey = `${n}:${observed ? "up" : "down"}`;
      if (nextImmediateSent[n] !== directionKey) {
        alerts.push(
          `⚡ BTC 장중 교차 포착 (미확정)\n` +
          `BTCUSDT ${fmt(live.price)}\n` +
          `MA${n} ${fmt(live.mas[n])} ${observed ? ">" : "<"} MA120 ${fmt(live.mas[120])}\n` +
          `${observed ? "상향돌파" : "하향돌파"} 감지 · 1분차\n` +
          `3분 유지 여부를 계속 확인합니다.`
        );
        nextImmediateSent[n] = directionKey;
      }

      if (nextCandidates[n].streak >= 3) {
        const before = targetPosition(stable);
        nextStable[n] = observed;
        const after = targetPosition(nextStable);
        confirmedAlerts.push(
          `✅ BTC 교차 3분 유지 확인\n` +
          `MA${n} ${observed ? "↑" : "↓"} MA120\n` +
          `BTCUSDT ${fmt(live.price)}\n` +
          `MA${n} ${fmt(live.mas[n])} / MA120 ${fmt(live.mas[120])}\n` +
          `전략 참고 비중: ${Math.round(before * 100)}% → ${Math.round(after * 100)}%\n` +
          `※ 장중 신호이며 일봉 종가 확정 전입니다.`
        );
        delete nextCandidates[n];
        delete nextImmediateSent[n];
      }
    }

    for (const text of [...alerts, ...confirmedAlerts]) await sendTelegram(text);

    const update = {
      stableRelations: nextStable,
      candidates: nextCandidates,
      immediateSent: nextImmediateSent,
      live: {
        price: live.price,
        ma5: live.mas[5],
        ma20: live.mas[20],
        ma65: live.mas[65],
        ma120: live.mas[120],
      },
      updatedAt: FieldValue.serverTimestamp(),
    };

    if (kst.hour === 9 && kst.minute === 0 && state.lastDailySummaryDate !== kst.date) {
      const prevDaily = state.dailyRelations || closed.rel;
      const changes = [];
      for (const n of SIGNAL_MAS) {
        if (Boolean(prevDaily[n]) !== Boolean(closed.rel[n])) {
          changes.push(`MA${n} ${closed.rel[n] ? "↑" : "↓"} MA120`);
        }
      }
      const order = [
        ["MA5", closed.mas[5]],
        ["MA20", closed.mas[20]],
        ["MA65", closed.mas[65]],
        ["MA120", closed.mas[120]],
      ].sort((a, b) => b[1] - a[1]).map((x) => x[0]).join(" > ");
      await sendTelegram(
        `🕘 BTC 일봉 종가 확정 (${kst.date})\n` +
        `종가 ${fmt(closed.price)}\n` +
        `MA5 ${fmt(closed.mas[5])}\nMA20 ${fmt(closed.mas[20])}\nMA65 ${fmt(closed.mas[65])}\nMA120 ${fmt(closed.mas[120])}\n` +
        `배열: ${order}\n` +
        `확정 변화: ${changes.length ? changes.join(", ") : "없음"}\n` +
        `전략 참고 비중: ${Math.round(targetPosition(closed.rel) * 100)}%`
      );
      update.lastDailySummaryDate = kst.date;
      update.dailyRelations = closed.rel;
    }

    await STATE_REF.set(update, { merge: true });
  }
);
