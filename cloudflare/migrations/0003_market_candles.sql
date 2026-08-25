CREATE TABLE IF NOT EXISTS market_candles (
  open_time INTEGER PRIMARY KEY,
  close_time INTEGER NOT NULL,
  close REAL NOT NULL,
  updated_at TEXT NOT NULL
);

DROP TABLE IF EXISTS setup_values;
