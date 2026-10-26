-- Health reports and player reports (src/reports.js). Safe to run again. Kept apart from schema.sql, which
-- re-checks every run row each time it is applied. Nothing here is ever served to a page.

-- One health report per player per day (a random health ID, never the log's install ID).
CREATE TABLE IF NOT EXISTS health_reports (
  id TEXT NOT NULL, day TEXT NOT NULL, received TEXT NOT NULL, conn TEXT NOT NULL, body TEXT NOT NULL,
  PRIMARY KEY (id, day)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS health_received ON health_reports (received);

-- What a player typed in "Send report" plus the scrubbed bug-report text. Read only by the owner.
CREATE TABLE IF NOT EXISTS user_reports (
  n INTEGER PRIMARY KEY, id TEXT NOT NULL, received TEXT NOT NULL, conn TEXT NOT NULL, version TEXT NOT NULL,
  message TEXT NOT NULL, details TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS user_reports_received ON user_reports (received);

-- Daily counters for the limits: keys like "h:conn:<code>", "h:site", "r:id:<id>", "r:conn:<code>", "r:site".
CREATE TABLE IF NOT EXISTS limits (
  day TEXT NOT NULL, key TEXT NOT NULL, n INTEGER NOT NULL,
  PRIMARY KEY (day, key)
) WITHOUT ROWID;
