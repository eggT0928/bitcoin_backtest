"use strict";

const crypto = require("node:crypto");
const { onSchedule } = require("firebase-functions/v2/scheduler");
const { defineSecret } = require("firebase-functions/params");
const { initializeApp } = require("firebase-admin/app");
const { FieldValue, Timestamp, getFirestore } = require("firebase-admin/firestore");
const { calcSnapshot, deliverClaimedEvent, processMinute } = require("./signal-engine");

initializeApp();
const db = getFirestore();

const TELEGRAM_BOT_TOKEN = defineSecret("TELEGRAM_BOT_TOKEN");
const TELEGRAM_CHAT_ID = defineSecret("TELEGRAM_CHAT_ID");

const SYMBOL = "BTCUSDT";
const STATE_REF = db.collection("btcAlerts").doc("state");
const OUTBOX = db.collection("btcAlertEvents");
const DELIVERY_LEASE_MS = 2 * 60 * 1000;

async function fetchDailyKlines() {
  const url = `https://api.binance.com/api/v3/klines?symbol=${SYMBOL}&interval=1d&limit=130`;
  const response = await fetch(url, { headers: { "User-Agent": "btc-ma-alert/2.0" } });
  if (!response.ok) throw new Error(`Binance HTTP ${response.status}`);
  const rows = await response.json();
  if (!Array.isArray(rows)) throw new Error("Binance 응답 형식이 올바르지 않습니다.");
  return rows.map((row) => ({
    openTime: Number(row[0]),
    close: Number(row[4]),
    closeTime: Number(row[6]),
  }));
}

async function sendTelegram(text) {
  const token = TELEGRAM_BOT_TOKEN.value();
  const chatId = TELEGRAM_CHAT_ID.value();
  const response = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text, disable_web_page_preview: true }),
  });
  const body = await response.text();
  if (!response.ok) throw new Error(`Telegram HTTP ${response.status}: ${body.slice(0, 300)}`);
  const parsed = JSON.parse(body);
  if (!parsed.ok) throw new Error(`Telegram API 오류: ${body.slice(0, 300)}`);
}

async function claimEvent(ref, leaseOwner) {
  return db.runTransaction(async (transaction) => {
    const snapshot = await transaction.get(ref);
    if (!snapshot.exists) return null;
    const event = snapshot.data();
    if (event.status === "sent") return null;
    const leaseUntil = event.leaseUntil?.toMillis?.() || 0;
    if (event.status === "delivering" && leaseUntil > Date.now()) return null;
    transaction.update(ref, {
      status: "delivering",
      leaseOwner,
      leaseUntil: Timestamp.fromMillis(Date.now() + DELIVERY_LEASE_MS),
      attempts: Number(event.attempts || 0) + 1,
      lastAttemptAt: FieldValue.serverTimestamp(),
    });
    return { id: ref.id, text: event.text };
  });
}

async function drainOutbox() {
  const leaseOwner = crypto.randomUUID();
  const snapshot = await OUTBOX.where("status", "in", ["pending", "delivering"]).limit(20).get();
  for (const document of snapshot.docs) {
    const event = await claimEvent(document.ref, leaseOwner);
    if (!event) continue;
    const result = await deliverClaimedEvent(event, {
      send: sendTelegram,
      markSent: async () => document.ref.update({
        status: "sent",
        sentAt: FieldValue.serverTimestamp(),
        leaseOwner: FieldValue.delete(),
        leaseUntil: FieldValue.delete(),
        lastError: FieldValue.delete(),
      }),
      markRetry: async (_id, error) => document.ref.update({
        status: "pending",
        leaseOwner: FieldValue.delete(),
        leaseUntil: FieldValue.delete(),
        lastError: String(error?.message || error).slice(0, 500),
      }),
    });
    if (result === "retry") console.error(`Telegram 전송 재시도 예정: ${event.id}`);
  }
}

async function persistObservation(live, closed, minuteKey) {
  return db.runTransaction(async (transaction) => {
    const snapshot = await transaction.get(STATE_REF);
    const previousState = snapshot.exists ? snapshot.data() : {};
    const result = processMinute(previousState, { live, closed, minuteKey });
    if (result.duplicate) return false;

    transaction.set(STATE_REF, {
      ...result.state,
      updatedAt: FieldValue.serverTimestamp(),
    }, { merge: true });
    for (const event of result.events) {
      transaction.create(OUTBOX.doc(event.id), {
        ...event,
        status: "pending",
        attempts: 0,
        createdAt: FieldValue.serverTimestamp(),
      });
    }
    return true;
  });
}

exports.checkBtcMaSignals = onSchedule(
  {
    schedule: "* * * * *",
    timeZone: "Asia/Seoul",
    region: "asia-northeast3",
    timeoutSeconds: 60,
    memory: "256MiB",
    secrets: [TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID],
  },
  async () => {
    const now = Date.now();
    const minuteKey = new Date(now).toISOString().slice(0, 16);
    const rows = await fetchDailyKlines();
    const live = calcSnapshot(rows, true, now);
    const closed = calcSnapshot(rows, false, now);
    await persistObservation(live, closed, minuteKey);
    await drainOutbox();
  },
);
