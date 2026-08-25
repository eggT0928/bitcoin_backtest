const url = "https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=130";
const response = await fetch(url, { headers: { Accept: "application/json" } });
if (!response.ok) throw new Error(`Binance HTTP ${response.status}`);

const rows = await response.json();
if (!Array.isArray(rows) || rows.length < 120) {
  throw new Error(`Binance 일봉 데이터가 부족합니다: ${Array.isArray(rows) ? rows.length : 0}`);
}

const updatedAt = new Date().toISOString();
console.log("BEGIN TRANSACTION;");
for (const row of rows) {
  const openTime = Number(row[0]);
  const close = Number(row[4]);
  const closeTime = Number(row[6]);
  if (![openTime, close, closeTime].every(Number.isFinite)) throw new Error("잘못된 Binance 일봉 데이터입니다");
  console.log(
    `INSERT OR REPLACE INTO market_candles (open_time, close_time, close, updated_at) ` +
    `VALUES (${openTime}, ${closeTime}, ${close}, '${updatedAt}');`,
  );
}
console.log("COMMIT;");
