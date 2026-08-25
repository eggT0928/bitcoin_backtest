CREATE TABLE IF NOT EXISTS alert_state (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  state_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alert_events (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  text TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'delivering', 'sent')),
  attempts INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  last_attempt_at TEXT,
  sent_at TEXT,
  lease_owner TEXT,
  lease_until INTEGER,
  last_error TEXT
);

CREATE INDEX IF NOT EXISTS idx_alert_events_delivery
ON alert_events(status, lease_until);
