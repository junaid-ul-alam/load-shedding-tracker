"""
Load Shedding Tracker - Flask Backend
======================================
Local dev:
    pip install -r requirements.txt
    python app.py
    Open: http://127.0.0.1:5000

Production (Render/Railway/etc):
    Start command: gunicorn app:app
"""

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
import os

app = Flask(__name__)
CORS(app)

# ──────────────────────────────────────────────
#  DATABASE PATH
#  On Render's free tier, the filesystem is
#  ephemeral (resets on redeploy). SQLite data
#  will persist between requests in a single
#  deployment but will reset on redeploy.
#  For persistent storage, migrate to a managed
#  DB (e.g. Render PostgreSQL, Supabase, etc.)
# ──────────────────────────────────────────────
DB_FILE = os.environ.get("DB_FILE", "load_shedding.db")


# ──────────────────────────────────────────────
#  HELPER: get a database connection
# ──────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


# ──────────────────────────────────────────────
#  SETUP: create tables and insert sample data
#  (runs automatically when app starts)
# ──────────────────────────────────────────────
def setup_database():
    conn = get_db()

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS locations (
            location_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            area_name      TEXT    NOT NULL,
            city           TEXT    NOT NULL,
            current_status TEXT    DEFAULT 'UNKNOWN'
        );

        CREATE TABLE IF NOT EXISTS users (
            user_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            username  TEXT    NOT NULL,
            area_id   INTEGER,
            FOREIGN KEY (area_id) REFERENCES locations(location_id)
        );

        CREATE TABLE IF NOT EXISTS reports (
            report_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            location_id     INTEGER NOT NULL,
            status_reported TEXT    NOT NULL,
            report_time     TEXT    DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id)     REFERENCES users(user_id),
            FOREIGN KEY (location_id) REFERENCES locations(location_id)
        );
    """)

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

    if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        conn.execute("INSERT INTO users (username, area_id) VALUES ('demo_user', 1)")
        print("✅ Demo user added.")

    conn.commit()
    conn.close()
    print("✅ Database ready:", DB_FILE)


# ──────────────────────────────────────────────
#  HELPER: recalculate majority vote for an area
# ──────────────────────────────────────────────
def recalculate_status(location_id):
    conn = get_db()

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


# ══════════════════════════════════════════════
#  ROUTE 1  GET /
# ══════════════════════════════════════════════
@app.route("/")
def home():
    return render_template("index.html")


# ══════════════════════════════════════════════
#  ROUTE 2  GET /locations
# ══════════════════════════════════════════════
@app.route("/locations", methods=["GET"])
def get_locations():
    conn = get_db()
    rows = conn.execute(
        "SELECT location_id, area_name, city, current_status FROM locations ORDER BY area_name"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ══════════════════════════════════════════════
#  ROUTE 3  GET /status/<location_id>
# ══════════════════════════════════════════════
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


# ══════════════════════════════════════════════
#  ROUTE 4  GET /votes/<location_id>
# ══════════════════════════════════════════════
@app.route("/votes/<int:location_id>", methods=["GET"])
def get_votes(location_id):
    conn = get_db()

    row = conn.execute("""
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


# ══════════════════════════════════════════════
#  ROUTE 5  GET /votes/all
# ══════════════════════════════════════════════
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
            COUNT(r.report_id) AS total_votes
        FROM locations l
        LEFT JOIN reports r
               ON l.location_id = r.location_id
              AND r.report_time >= datetime('now', 'localtime', '-15 minutes')
        GROUP BY l.location_id, l.area_name, l.current_status
        ORDER BY l.area_name
    """).fetchall()

    conn.close()
    return jsonify([dict(r) for r in rows])


# ══════════════════════════════════════════════
#  ROUTE 6  GET /recent/<location_id>
# ══════════════════════════════════════════════
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


# ══════════════════════════════════════════════
#  ROUTE 7  POST /report
# ══════════════════════════════════════════════
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

    conn.execute("""
        INSERT INTO reports (user_id, location_id, status_reported)
        VALUES (?, ?, ?)
    """, (user_id, location_id, status))
    conn.commit()
    conn.close()

    new_status = recalculate_status(location_id)

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


# ──────────────────────────────────────────────
#  START
#  gunicorn calls app directly — this block only
#  runs for local `python app.py` development.
# ──────────────────────────────────────────────
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

    print("\n" + "="*50)
    print("  ⚡ Load Shedding Tracker is running!")
    print("="*50)
    print(f"  💻 On this PC     → http://127.0.0.1:{port}")
    print(f"  📱 On mobile/WiFi → http://{local_ip}:{port}")
    print("="*50)
    print("  Press CTRL+C to stop the server\n")

    app.run(host="0.0.0.0", port=port, debug=False)
