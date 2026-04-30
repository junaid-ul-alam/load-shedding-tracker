"""
Smart Load Shedding Tracker - Flask Backend
============================================
DBMS Concepts Implemented:
  [CONSTRAINT]     NOT NULL, UNIQUE, CHECK on tables
  [MANY-TO-MANY]   subscriptions table (users ↔ locations)
  [TRIGGER]        auto-logs every INSERT on reports → report_logs
  [AGG FUNCTIONS]  COUNT, MAX, SUM, ROUND in multiple queries
  [CALC FIELD]     confidence_pct computed inline via SQL
  [NORMALIZATION]  3NF — no repeating groups, no transitive deps
  [FK INTEGRITY]   PRAGMA foreign_keys = ON enforced per connection

How to run:
    pip install flask flask-cors
    python app.py
Then open: http://127.0.0.1:5000
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
import os

app = Flask(__name__)
CORS(app)

DB_FILE = os.environ.get("DB_FILE", "load_shedding.db")


# ──────────────────────────────────────────────────────────────
#  HELPER: get a database connection
#
#  [FK INTEGRITY] — PRAGMA foreign_keys = ON must be set per
#  connection in SQLite; it is OFF by default. Without this line,
#  foreign key violations would be silently ignored.
# ──────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")   # [FK INTEGRITY]
    return conn


# ──────────────────────────────────────────────────────────────
#  SETUP: create all tables, trigger, and seed data
# ──────────────────────────────────────────────────────────────
def setup_database():
    conn = get_db()

    # ── executescript turns off auto-commit, so we commit manually
    conn.executescript("""

        -- ════════════════════════════════════════════
        --  TABLE: locations
        --  [CONSTRAINT] NOT NULL on area_name, city
        --  [NORMALIZATION] city is stored once per
        --    location row — no separate cities table
        --    needed because city is an attribute OF
        --    the location (no transitive dependency).
        -- ════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS locations (
            location_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            area_name      TEXT    NOT NULL,                -- [CONSTRAINT] NOT NULL
            city           TEXT    NOT NULL,                -- [CONSTRAINT] NOT NULL
            current_status TEXT    NOT NULL DEFAULT 'UNKNOWN',
            -- [CONSTRAINT] CHECK — only these 3 values allowed in this column
            CHECK (current_status IN ('ON', 'OFF', 'UNKNOWN'))
        );

        -- ════════════════════════════════════════════
        --  TABLE: users
        --  [CONSTRAINT] UNIQUE on username — no two
        --    users can share the same name
        --  [NORMALIZATION] area_id is a FK, not a
        --    repeated text field (avoids redundancy)
        -- ════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS users (
            user_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            username  TEXT    NOT NULL UNIQUE,              -- [CONSTRAINT] NOT NULL + UNIQUE
            area_id   INTEGER,
            FOREIGN KEY (area_id) REFERENCES locations(location_id)
                ON DELETE SET NULL                         -- [FK INTEGRITY] graceful delete
        );

        -- ════════════════════════════════════════════
        --  TABLE: reports
        --  [CONSTRAINT] CHECK — status must be ON/OFF
        --  [FK INTEGRITY] both FK columns are NOT NULL
        --    and reference valid parent rows
        -- ════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS reports (
            report_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,               -- [CONSTRAINT] NOT NULL
            location_id     INTEGER NOT NULL,               -- [CONSTRAINT] NOT NULL
            status_reported TEXT    NOT NULL,               -- [CONSTRAINT] NOT NULL
            report_time     TEXT    NOT NULL
                            DEFAULT (datetime('now','localtime')),
            -- [CONSTRAINT] CHECK — prevents any value other than 'ON' or 'OFF'
            CHECK (status_reported IN ('ON', 'OFF')),
            FOREIGN KEY (user_id)     REFERENCES users(user_id)
                ON DELETE CASCADE,                         -- [FK INTEGRITY]
            FOREIGN KEY (location_id) REFERENCES locations(location_id)
                ON DELETE CASCADE                          -- [FK INTEGRITY]
        );

        -- ════════════════════════════════════════════
        --  TABLE: subscriptions   [MANY-TO-MANY]
        --
        --  A user can follow many locations.
        --  A location can be followed by many users.
        --  This junction table resolves the M:N
        --  relationship into two 1:N relationships.
        --
        --  [CONSTRAINT] UNIQUE(user_id, location_id)
        --    prevents a user from subscribing twice
        --    to the same location.
        --  [NORMALIZATION] No extra columns here that
        --    belong to users or locations (3NF clean).
        -- ════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS subscriptions (
            sub_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,                 -- [CONSTRAINT] NOT NULL
            location_id   INTEGER NOT NULL,                 -- [CONSTRAINT] NOT NULL
            subscribed_at TEXT    NOT NULL
                          DEFAULT (datetime('now','localtime')),
            -- [CONSTRAINT] UNIQUE composite key — one row per user+location pair
            UNIQUE (user_id, location_id),
            FOREIGN KEY (user_id)     REFERENCES users(user_id)
                ON DELETE CASCADE,                         -- [FK INTEGRITY]
            FOREIGN KEY (location_id) REFERENCES locations(location_id)
                ON DELETE CASCADE                          -- [FK INTEGRITY]
        );

        -- ════════════════════════════════════════════
        --  TABLE: report_logs     [TRIGGER target]
        --
        --  Stores an audit trail of every report
        --  insertion. Populated automatically by the
        --  trigger below — never written to directly.
        --  [NORMALIZATION] Separated from reports to
        --    avoid repeating data; log_time may differ
        --    from report_time if server clock shifts.
        -- ════════════════════════════════════════════
        CREATE TABLE IF NOT EXISTS report_logs (
            log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            report_id   INTEGER NOT NULL,                  -- FK to the original report
            user_id     INTEGER NOT NULL,
            location_id INTEGER NOT NULL,
            status_reported TEXT NOT NULL,
            action      TEXT    NOT NULL DEFAULT 'INSERT', -- what happened
            log_time    TEXT    NOT NULL
                        DEFAULT (datetime('now','localtime'))
            -- No FK to reports here intentionally: logs should survive
            -- even if the original report is later deleted (audit trail).
        );

        -- ════════════════════════════════════════════
        --  TRIGGER: trg_log_report_insert   [TRIGGER]
        --
        --  Fires automatically AFTER every INSERT on
        --  the reports table. Copies key fields into
        --  report_logs so we have a permanent audit
        --  log without any extra application code.
        --
        --  NEW.column_name refers to the row just
        --  inserted into reports.
        -- ════════════════════════════════════════════
        CREATE TRIGGER IF NOT EXISTS trg_log_report_insert
        AFTER INSERT ON reports
        FOR EACH ROW
        BEGIN
            INSERT INTO report_logs (
                report_id, user_id, location_id,
                status_reported, action
            ) VALUES (
                NEW.report_id,
                NEW.user_id,
                NEW.location_id,
                NEW.status_reported,
                'INSERT'
            );
        END;

    """)

    # ── Seed locations (only if empty)
    count = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
    if count == 0:
        conn.executemany(
            "INSERT INTO locations (area_name, city) VALUES (?, ?)",
            [
                ("Mirpur",       "Dhaka"),
                ("Dhanmondi",    "Dhaka"),
                ("Gulshan",      "Dhaka"),
                ("Uttara",       "Dhaka"),
                ("Motijheel",    "Dhaka"),
                ("Banani",       "Dhaka"),
                ("Mohammadpur",  "Dhaka"),
                ("Rampura",      "Dhaka"),
                ("Badda",        "Dhaka"),
                ("Pallabi",      "Dhaka"),
            ]
        )
        print("✅ 10 locations added.")

    # ── Seed demo user (only if empty)
    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO users (username, area_id) VALUES ('demo_user', 1)"
        )
        print("✅ Demo user added.")

    conn.commit()
    conn.close()
    print("✅ Database ready:", DB_FILE)


# ──────────────────────────────────────────────────────────────
#  HELPER: recalculate majority vote for one area
#  [AGG FUNCTIONS] SUM with CASE = conditional aggregation
# ──────────────────────────────────────────────────────────────
def recalculate_status(location_id):
    conn = get_db()

    # [AGG FUNCTIONS] SUM(CASE …) counts ON and OFF votes separately
    row = conn.execute("""
        SELECT
            SUM(CASE WHEN status_reported = 'OFF' THEN 1 ELSE 0 END) AS off_votes,
            SUM(CASE WHEN status_reported = 'ON'  THEN 1 ELSE 0 END) AS on_votes
        FROM reports
        WHERE location_id = ?
          AND report_time >= datetime('now', 'localtime', '-15 minutes')
    """, (location_id,)).fetchone()

    off_votes = row["off_votes"] or 0
    on_votes  = row["on_votes"]  or 0

    if   off_votes > on_votes: new_status = "OFF"
    elif on_votes > off_votes: new_status = "ON"
    else:                      new_status = "UNKNOWN"

    conn.execute(
        "UPDATE locations SET current_status = ? WHERE location_id = ?",
        (new_status, location_id)
    )
    conn.commit()
    conn.close()
    return new_status


# ══════════════════════════════════════════════════════════════
#  ROUTE 1  GET /
# ══════════════════════════════════════════════════════════════
@app.route("/")
def home():
    return render_template("index.html")


# ══════════════════════════════════════════════════════════════
#  ROUTE 2  GET /locations
#  Returns all locations as JSON
# ══════════════════════════════════════════════════════════════
@app.route("/locations", methods=["GET"])
def get_locations():
    conn = get_db()
    rows = conn.execute(
        "SELECT location_id, area_name, city, current_status "
        "FROM locations ORDER BY area_name"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ══════════════════════════════════════════════════════════════
#  ROUTE 3  GET /status/<location_id>
# ══════════════════════════════════════════════════════════════
@app.route("/status/<int:location_id>", methods=["GET"])
def get_status(location_id):
    conn = get_db()
    row = conn.execute(
        "SELECT area_name, city, current_status FROM locations WHERE location_id = ?",
        (location_id,)
    ).fetchone()
    conn.close()

    if row is None:
        return jsonify({"error": "Location not found"}), 404

    return jsonify(dict(row))


# ══════════════════════════════════════════════════════════════
#  ROUTE 4  GET /votes/<location_id>
#
#  [AGG FUNCTIONS]
#    COUNT(CASE …)   — conditional count for ON / OFF
#    COUNT(*)        — total reports
#    MAX(report_time)— most recent timestamp
#
#  [CALC FIELD] confidence_pct is computed entirely in SQL:
#    majority_count / total * 100
#    CASE guards division by zero when total = 0
# ══════════════════════════════════════════════════════════════
@app.route("/votes/<int:location_id>", methods=["GET"])
def get_votes(location_id):
    conn = get_db()

    row = conn.execute("""
        SELECT
            -- [AGG FUNCTIONS] COUNT with CASE = conditional aggregation
            COUNT(CASE WHEN status_reported = 'ON'  THEN 1 END) AS on_votes,
            COUNT(CASE WHEN status_reported = 'OFF' THEN 1 END) AS off_votes,
            COUNT(*)                                             AS total_votes,

            -- [CALC FIELD] confidence_pct — inline calculated field
            -- Formula: (higher of on_votes / off_votes) / total * 100
            -- CASE prevents division-by-zero when no reports exist
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

            -- [AGG FUNCTIONS] MAX returns the latest report timestamp
            MAX(report_time) AS last_report_time

        FROM reports
        WHERE location_id = ?
          AND report_time >= datetime('now', 'localtime', '-15 minutes')
    """, (location_id,)).fetchone()

    conn.close()

    return jsonify({
        "location_id":      location_id,
        "on_votes":         row["on_votes"],
        "off_votes":        row["off_votes"],
        "total_votes":      row["total_votes"],
        "confidence_pct":   row["confidence_pct"],
        "last_report_time": row["last_report_time"],
        "window":           "last 15 minutes"
    })


# ══════════════════════════════════════════════════════════════
#  ROUTE 5  GET /votes/all
#  [AGG FUNCTIONS] GROUP BY — one aggregate row per location
#  [FK INTEGRITY]  LEFT JOIN keeps locations with 0 reports
# ══════════════════════════════════════════════════════════════
@app.route("/votes/all", methods=["GET"])
def get_votes_all():
    conn = get_db()

    rows = conn.execute("""
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
        GROUP BY l.location_id, l.area_name, l.current_status   -- [AGG FUNCTIONS] GROUP BY
        ORDER BY l.area_name
    """).fetchall()

    conn.close()
    return jsonify([dict(r) for r in rows])


# ══════════════════════════════════════════════════════════════
#  ROUTE 6  GET /recent/<location_id>
#  Returns last 5 reports (JOIN pulls username from users)
# ══════════════════════════════════════════════════════════════
@app.route("/recent/<int:location_id>", methods=["GET"])
def get_recent(location_id):
    conn = get_db()

    rows = conn.execute("""
        SELECT
            r.report_id,
            u.username,
            r.status_reported,
            r.report_time
        FROM   reports r
        JOIN   users   u ON r.user_id = u.user_id
        WHERE  r.location_id = ?
        ORDER BY r.report_time DESC
        LIMIT 5
    """, (location_id,)).fetchall()

    conn.close()
    return jsonify([dict(r) for r in rows])


# ══════════════════════════════════════════════════════════════
#  ROUTE 7  POST /report
#  [TRIGGER] The INSERT below automatically fires
#            trg_log_report_insert → writes to report_logs
#  [CONSTRAINT] CHECK on status_reported enforced by DB
# ══════════════════════════════════════════════════════════════
@app.route("/report", methods=["POST"])
def submit_report():
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data sent. Send JSON."}), 400

    user_id     = data.get("user_id")
    location_id = data.get("location_id")
    status      = str(data.get("status", "")).upper().strip()

    if not user_id or not location_id:
        return jsonify({"error": "user_id and location_id are required"}), 400
    if status not in ("ON", "OFF"):
        return jsonify({"error": "status must be ON or OFF"}), 400

    conn = get_db()

    # Duplicate check: one report per user per location per 10 minutes
    recent = conn.execute("""
        SELECT COUNT(*) AS cnt
        FROM   reports
        WHERE  user_id     = ?
          AND  location_id = ?
          AND  report_time >= datetime('now', 'localtime', '-10 minutes')
    """, (user_id, location_id)).fetchone()

    if recent["cnt"] > 0:
        conn.close()
        return jsonify({
            "error": "You already reported this area in the last 10 minutes. Please wait."
        }), 429

    # [TRIGGER] This INSERT fires trg_log_report_insert automatically.
    # The trigger writes a copy to report_logs — no extra code needed here.
    # [CONSTRAINT] The CHECK(status_reported IN ('ON','OFF')) also fires here.
    conn.execute("""
        INSERT INTO reports (user_id, location_id, status_reported)
        VALUES (?, ?, ?)
    """, (user_id, location_id, status))
    conn.commit()
    conn.close()

    new_status = recalculate_status(location_id)

    # Fetch updated vote counts to return in the same response
    conn2 = get_db()
    vote_row = conn2.execute("""
        SELECT
            COUNT(CASE WHEN status_reported = 'ON'  THEN 1 END) AS on_votes,
            COUNT(CASE WHEN status_reported = 'OFF' THEN 1 END) AS off_votes,
            COUNT(*) AS total_votes,
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
            MAX(report_time) AS last_report_time
        FROM reports
        WHERE location_id = ?
          AND report_time >= datetime('now', 'localtime', '-15 minutes')
    """, (location_id,)).fetchone()
    conn2.close()

    return jsonify({
        "message":          "Report submitted!",
        "your_vote":        status,
        "area_status_now":  new_status,
        "on_votes":         vote_row["on_votes"],
        "off_votes":        vote_row["off_votes"],
        "total_votes":      vote_row["total_votes"],
        "confidence_pct":   vote_row["confidence_pct"],
        "last_report_time": vote_row["last_report_time"]
    }), 201


# ══════════════════════════════════════════════════════════════
#  ROUTE 8  POST /subscribe
#  [MANY-TO-MANY] Add a user↔location subscription
#
#  Expected JSON body:
#  { "user_id": 1, "location_id": 3 }
# ══════════════════════════════════════════════════════════════
@app.route("/subscribe", methods=["POST"])
def subscribe():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data sent."}), 400

    user_id     = data.get("user_id")
    location_id = data.get("location_id")

    if not user_id or not location_id:
        return jsonify({"error": "user_id and location_id are required"}), 400

    conn = get_db()
    try:
        # [MANY-TO-MANY] INSERT into junction table
        # [CONSTRAINT] UNIQUE(user_id, location_id) prevents duplicates —
        #   SQLite raises IntegrityError if the pair already exists.
        conn.execute("""
            INSERT INTO subscriptions (user_id, location_id)
            VALUES (?, ?)
        """, (user_id, location_id))
        conn.commit()
        conn.close()
        return jsonify({"message": "Subscribed successfully!"}), 201

    except Exception as e:
        conn.close()
        # IntegrityError means the UNIQUE constraint was violated
        if "UNIQUE" in str(e):
            return jsonify({"error": "Already subscribed to this location."}), 409
        return jsonify({"error": str(e)}), 400


# ══════════════════════════════════════════════════════════════
#  ROUTE 9  DELETE /subscribe
#  [MANY-TO-MANY] Remove a user↔location subscription
#
#  Expected JSON body:
#  { "user_id": 1, "location_id": 3 }
# ══════════════════════════════════════════════════════════════
@app.route("/subscribe", methods=["DELETE"])
def unsubscribe():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data sent."}), 400

    user_id     = data.get("user_id")
    location_id = data.get("location_id")

    if not user_id or not location_id:
        return jsonify({"error": "user_id and location_id are required"}), 400

    conn = get_db()
    conn.execute(
        "DELETE FROM subscriptions WHERE user_id = ? AND location_id = ?",
        (user_id, location_id)
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "Unsubscribed successfully."}), 200


# ══════════════════════════════════════════════════════════════
#  ROUTE 10  GET /subscriptions/<user_id>
#  [MANY-TO-MANY] List all locations a user follows
#  Uses JOIN across the junction table to get location details
# ══════════════════════════════════════════════════════════════
@app.route("/subscriptions/<int:user_id>", methods=["GET"])
def get_subscriptions(user_id):
    conn = get_db()

    # [MANY-TO-MANY] JOIN: users → subscriptions → locations
    rows = conn.execute("""
        SELECT
            l.location_id,
            l.area_name,
            l.city,
            l.current_status,
            s.subscribed_at
        FROM   subscriptions s
        JOIN   locations     l ON s.location_id = l.location_id
        WHERE  s.user_id = ?
        ORDER BY l.area_name
    """, (user_id,)).fetchall()

    conn.close()
    return jsonify([dict(r) for r in rows])


# ══════════════════════════════════════════════════════════════
#  ROUTE 11  GET /logs/<location_id>
#  [TRIGGER] View the audit log generated by the trigger
#  Shows last 10 report events for a location
# ══════════════════════════════════════════════════════════════
@app.route("/logs/<int:location_id>", methods=["GET"])
def get_logs(location_id):
    conn = get_db()

    # [TRIGGER] report_logs is populated automatically by the DB trigger.
    # This route just reads what the trigger recorded.
    rows = conn.execute("""
        SELECT
            rl.log_id,
            rl.report_id,
            u.username,
            rl.status_reported,
            rl.action,
            rl.log_time
        FROM   report_logs rl
        JOIN   users       u ON rl.user_id = u.user_id
        WHERE  rl.location_id = ?
        ORDER BY rl.log_time DESC
        LIMIT 10
    """, (location_id,)).fetchall()

    conn.close()
    return jsonify([dict(r) for r in rows])


# ══════════════════════════════════════════════════════════════
#  ROUTE 12  GET /stats
#  [AGG FUNCTIONS] + [CALC FIELD] — system-wide summary stats
#  Uses COUNT, MAX, GROUP BY across all tables
# ══════════════════════════════════════════════════════════════
@app.route("/stats", methods=["GET"])
def get_stats():
    conn = get_db()

    # [AGG FUNCTIONS] system-wide counts
    totals = conn.execute("""
        SELECT
            COUNT(*)                                              AS total_reports,
            COUNT(CASE WHEN status_reported = 'ON'  THEN 1 END)  AS total_on,
            COUNT(CASE WHEN status_reported = 'OFF' THEN 1 END)  AS total_off,
            -- [CALC FIELD] off_rate: percentage of all reports that are OFF
            CASE
                WHEN COUNT(*) = 0 THEN 0
                ELSE ROUND(
                    CAST(COUNT(CASE WHEN status_reported='OFF' THEN 1 END) AS REAL)
                    / COUNT(*) * 100, 1
                )
            END AS off_rate_pct,
            MAX(report_time) AS last_report_time                -- [AGG FUNCTIONS] MAX
        FROM reports
    """).fetchone()

    # [AGG FUNCTIONS] most-reported area (GROUP BY + ORDER BY COUNT)
    busiest = conn.execute("""
        SELECT
            l.area_name,
            COUNT(r.report_id) AS report_count    -- [AGG FUNCTIONS] COUNT + GROUP BY
        FROM   locations l
        LEFT   JOIN reports r ON l.location_id = r.location_id
        GROUP  BY l.location_id, l.area_name
        ORDER  BY report_count DESC
        LIMIT  1
    """).fetchone()

    # [MANY-TO-MANY] subscription count
    sub_count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM subscriptions"
    ).fetchone()

    # [TRIGGER] total log entries (proof the trigger has been firing)
    log_count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM report_logs"
    ).fetchone()

    conn.close()

    return jsonify({
        "total_reports":    totals["total_reports"],
        "total_on":         totals["total_on"],
        "total_off":        totals["total_off"],
        "off_rate_pct":     totals["off_rate_pct"],
        "last_report_time": totals["last_report_time"],
        "busiest_area":     dict(busiest) if busiest else None,
        "total_subscriptions": sub_count["cnt"],
        "total_log_entries":   log_count["cnt"],   # [TRIGGER] proof of trigger writes
    })


# ──────────────────────────────────────────────────────────────
#  START
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    setup_database()

    port = int(os.environ.get("PORT", 5000))

    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
    except Exception:
        local_ip = "YOUR_PC_IP"

    print("\n" + "=" * 50)
    print("  ⚡ Smart Load Shedding Tracker")
    print("=" * 50)
    print(f"  💻 PC       → http://127.0.0.1:{port}")
    print(f"  📱 Mobile   → http://{local_ip}:{port}")
    print("=" * 50)
    print("  NEW endpoints:")
    print(f"  POST   /subscribe          [MANY-TO-MANY]")
    print(f"  DELETE /subscribe          [MANY-TO-MANY]")
    print(f"  GET    /subscriptions/<id> [MANY-TO-MANY]")
    print(f"  GET    /logs/<location_id> [TRIGGER logs]")
    print(f"  GET    /stats              [AGG FUNCTIONS]")
    print("=" * 50)
    print("  Press CTRL+C to stop\n")

    app.run(host="0.0.0.0", port=port, debug=False)
