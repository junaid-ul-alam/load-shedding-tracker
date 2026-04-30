-- ================================================================
--  Smart Load Shedding Tracker — Full Database Schema
--  Each DBMS concept is tagged with [CONCEPT NAME]
-- ================================================================

-- ──────────────────────────────────────────────────────────────
--  Always enable FK enforcement in SQLite (off by default)
--  [FK INTEGRITY]
-- ──────────────────────────────────────────────────────────────
PRAGMA foreign_keys = ON;


-- ════════════════════════════════════════════════════════
--  TABLE: locations
--
--  [CONSTRAINT] NOT NULL  — area_name, city, current_status
--  [CONSTRAINT] CHECK     — current_status must be one of
--                           'ON', 'OFF', 'UNKNOWN'
--  [NORMALIZATION 1NF]    — every cell is atomic (single value)
--  [NORMALIZATION 2NF]    — no partial dependencies (PK is single col)
--  [NORMALIZATION 3NF]    — no transitive dependencies;
--                           city describes the location, not
--                           something derived from another non-key col
-- ════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS locations (
    location_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    area_name      TEXT    NOT NULL,                    -- [CONSTRAINT] NOT NULL
    city           TEXT    NOT NULL,                    -- [CONSTRAINT] NOT NULL
    current_status TEXT    NOT NULL DEFAULT 'UNKNOWN',
    CHECK (current_status IN ('ON', 'OFF', 'UNKNOWN'))  -- [CONSTRAINT] CHECK
);


-- ════════════════════════════════════════════════════════
--  TABLE: users
--
--  [CONSTRAINT] NOT NULL  — username is required
--  [CONSTRAINT] UNIQUE    — no two users share a username
--  [FK INTEGRITY]         — area_id references locations
--  [NORMALIZATION 3NF]    — username does not depend on area_id
-- ════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS users (
    user_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    username  TEXT    NOT NULL UNIQUE,                  -- [CONSTRAINT] NOT NULL + UNIQUE
    area_id   INTEGER,
    FOREIGN KEY (area_id) REFERENCES locations(location_id)
        ON DELETE SET NULL                              -- [FK INTEGRITY]
);


-- ════════════════════════════════════════════════════════
--  TABLE: reports
--
--  [CONSTRAINT] NOT NULL  — user_id, location_id, status_reported
--  [CONSTRAINT] CHECK     — status_reported must be 'ON' or 'OFF'
--  [FK INTEGRITY]         — both FKs enforce referential integrity;
--                           CASCADE deletes child rows if parent removed
--  [NORMALIZATION 3NF]    — all columns depend only on report_id (PK)
-- ════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS reports (
    report_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,                   -- [CONSTRAINT] NOT NULL
    location_id     INTEGER NOT NULL,                   -- [CONSTRAINT] NOT NULL
    status_reported TEXT    NOT NULL,                   -- [CONSTRAINT] NOT NULL
    report_time     TEXT    NOT NULL
                    DEFAULT (datetime('now','localtime')),
    CHECK (status_reported IN ('ON', 'OFF')),            -- [CONSTRAINT] CHECK
    FOREIGN KEY (user_id)     REFERENCES users(user_id)
        ON DELETE CASCADE,                              -- [FK INTEGRITY]
    FOREIGN KEY (location_id) REFERENCES locations(location_id)
        ON DELETE CASCADE                               -- [FK INTEGRITY]
);


-- ════════════════════════════════════════════════════════
--  TABLE: subscriptions    [MANY-TO-MANY]
--
--  Implements the Many-to-Many relationship:
--    - One user   can follow  many locations
--    - One location can have  many followers (users)
--
--  This junction table resolves M:N into two 1:N:
--    users       1 ── ∞  subscriptions
--    locations   1 ── ∞  subscriptions
--
--  [CONSTRAINT] NOT NULL  — both FK columns required
--  [CONSTRAINT] UNIQUE    — composite key prevents duplicate subscriptions
--  [FK INTEGRITY]         — CASCADE removes subs when user/location deleted
--  [NORMALIZATION 3NF]    — only stores the relationship + timestamp,
--                           no user or location data is repeated here
-- ════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS subscriptions (
    sub_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL,                     -- [CONSTRAINT] NOT NULL
    location_id   INTEGER NOT NULL,                     -- [CONSTRAINT] NOT NULL
    subscribed_at TEXT    NOT NULL
                  DEFAULT (datetime('now','localtime')),
    UNIQUE (user_id, location_id),                      -- [CONSTRAINT] UNIQUE composite
    FOREIGN KEY (user_id)     REFERENCES users(user_id)
        ON DELETE CASCADE,                              -- [FK INTEGRITY]
    FOREIGN KEY (location_id) REFERENCES locations(location_id)
        ON DELETE CASCADE                               -- [FK INTEGRITY]
);


-- ════════════════════════════════════════════════════════
--  TABLE: report_logs      [TRIGGER target]
--
--  This table is never written to by application code.
--  It is populated exclusively by the trigger below.
--  Acts as a permanent audit trail.
--
--  [NORMALIZATION] Separated from reports to avoid mixing
--    audit metadata (log_time, action) with business data.
--    Follows 3NF — all columns depend on log_id (PK).
-- ════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS report_logs (
    log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id   INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    location_id INTEGER NOT NULL,
    status_reported TEXT NOT NULL,
    action      TEXT    NOT NULL DEFAULT 'INSERT',
    log_time    TEXT    NOT NULL
                DEFAULT (datetime('now','localtime'))
    -- Intentionally NO FK to reports:
    -- logs should survive even if the original report is deleted.
);


-- ════════════════════════════════════════════════════════
--  TRIGGER: trg_log_report_insert     [TRIGGER]
--
--  Fires automatically AFTER every INSERT on reports.
--  Copies key fields to report_logs so every report
--  is permanently audited without any application code.
--
--  NEW.column_name  = value just inserted into reports
-- ════════════════════════════════════════════════════════
CREATE TRIGGER IF NOT EXISTS trg_log_report_insert
AFTER INSERT ON reports
FOR EACH ROW
BEGIN
    INSERT INTO report_logs (
        report_id, user_id, location_id,
        status_reported, action
    ) VALUES (
        NEW.report_id,       -- the newly generated report_id
        NEW.user_id,
        NEW.location_id,
        NEW.status_reported,
        'INSERT'
    );
END;


-- ════════════════════════════════════════════════════════
--  EXAMPLE QUERIES SHOWING SQL CONCEPTS
-- ════════════════════════════════════════════════════════

-- [AGG FUNCTIONS] COUNT with CASE — conditional aggregation
-- Counts ON and OFF votes separately, computes confidence_pct
SELECT
    COUNT(CASE WHEN status_reported = 'ON'  THEN 1 END) AS on_votes,
    COUNT(CASE WHEN status_reported = 'OFF' THEN 1 END) AS off_votes,
    COUNT(*)                                             AS total_votes,

    -- [CALC FIELD] confidence_pct — fully computed in SQL
    CASE
        WHEN COUNT(*) = 0 THEN 0
        ELSE ROUND(
            CAST(
                MAX(
                    COUNT(CASE WHEN status_reported = 'ON'  THEN 1 END),
                    COUNT(CASE WHEN status_reported = 'OFF' THEN 1 END)
                ) AS REAL
            ) / COUNT(*) * 100, 1
        )
    END AS confidence_pct,

    MAX(report_time) AS last_report_time   -- [AGG FUNCTIONS] MAX
FROM reports
WHERE location_id = 1
  AND report_time >= datetime('now', 'localtime', '-15 minutes');


-- [MANY-TO-MANY] JOIN across the junction table
-- Lists all locations user 1 is following, with live status
SELECT
    l.location_id,
    l.area_name,
    l.city,
    l.current_status,
    s.subscribed_at
FROM   subscriptions s
JOIN   locations     l ON s.location_id = l.location_id
WHERE  s.user_id = 1
ORDER BY l.area_name;


-- [TRIGGER] Read the audit log — written by the trigger, not app code
SELECT
    rl.log_id,
    rl.report_id,
    u.username,
    rl.status_reported,
    rl.action,
    rl.log_time
FROM   report_logs rl
JOIN   users       u ON rl.user_id = u.user_id
ORDER BY rl.log_time DESC
LIMIT 10;


-- [AGG FUNCTIONS] GROUP BY — one row per location
-- Used in /votes/all to summarise all 10 areas in one query
SELECT
    l.location_id,
    l.area_name,
    l.current_status,
    COUNT(CASE WHEN r.status_reported = 'ON'  THEN 1 END) AS on_votes,
    COUNT(CASE WHEN r.status_reported = 'OFF' THEN 1 END) AS off_votes,
    COUNT(r.report_id)                                     AS total_votes
FROM locations l
LEFT JOIN reports r
       ON l.location_id = r.location_id
      AND r.report_time >= datetime('now', 'localtime', '-15 minutes')
GROUP BY l.location_id, l.area_name, l.current_status
ORDER BY l.area_name;
