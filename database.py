import sqlite3
from datetime import datetime, timedelta

DB_PATH = "osocare.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        line_id TEXT PRIMARY KEY,
        name TEXT,
        med_name TEXT DEFAULT 'ยาตามใบสั่ง',
        health_points INTEGER DEFAULT 0,
        registered_at TEXT,
        adr_mode INTEGER DEFAULT 0,
        awaiting_med INTEGER DEFAULT 0,
        health_log_mode INTEGER DEFAULT 0,
        health_log_type TEXT DEFAULT ''
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS medication_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        line_id TEXT,
        status TEXT,
        logged_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        line_id TEXT,
        level TEXT,
        message TEXT,
        adr_description TEXT,
        resolved INTEGER DEFAULT 0,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS redemptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        line_id TEXT,
        points_used INTEGER,
        discount_thb INTEGER,
        redeemed_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS health_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        line_id TEXT,
        log_type TEXT,
        value TEXT,
        logged_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS refill_subscriptions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        line_id TEXT,
        start_date TEXT,
        next_date TEXT,
        days_left INTEGER DEFAULT 30,
        active INTEGER DEFAULT 1
    )""")

    # Migrations สำหรับ DB เก่า
    for col, definition in [
        ("adr_mode",        "INTEGER DEFAULT 0"),
        ("awaiting_med",    "INTEGER DEFAULT 0"),
        ("health_log_mode", "INTEGER DEFAULT 0"),
        ("health_log_type", "TEXT DEFAULT ''"),
    ]:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
        except:
            pass

    try:
        c.execute("ALTER TABLE alerts ADD COLUMN adr_description TEXT")
    except:
        pass
    try:
        c.execute("ALTER TABLE alerts ADD COLUMN resolved INTEGER DEFAULT 0")
    except:
        pass

    conn.commit()
    conn.close()

# ── Users ──────────────────────────────────────────────────────────

def save_user(line_id):
    conn = get_conn()
    conn.execute("""INSERT OR IGNORE INTO users
        (line_id, registered_at) VALUES (?, ?)""",
        (line_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_user(line_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE line_id=?", (line_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

def update_user_name(line_id, name):
    conn = get_conn()
    conn.execute("UPDATE users SET name=? WHERE line_id=?", (name, line_id))
    conn.commit()
    conn.close()

def update_user_med(line_id, med_name):
    conn = get_conn()
    conn.execute("UPDATE users SET med_name=?, awaiting_med=0 WHERE line_id=?",
                 (med_name, line_id))
    conn.commit()
    conn.close()

def set_awaiting_med(line_id, val):
    conn = get_conn()
    conn.execute("UPDATE users SET awaiting_med=? WHERE line_id=?", (val, line_id))
    conn.commit()
    conn.close()

def set_adr_mode(line_id, val):
    conn = get_conn()
    conn.execute("UPDATE users SET adr_mode=? WHERE line_id=?", (val, line_id))
    conn.commit()
    conn.close()

def set_health_log_mode(line_id, val, log_type=""):
    conn = get_conn()
    conn.execute("UPDATE users SET health_log_mode=?, health_log_type=? WHERE line_id=?",
                 (val, log_type, line_id))
    conn.commit()
    conn.close()


def check_taken_today(line_id, date_str):
    """ตรวจว่า user กินยาวันนี้แล้วหรือยัง"""
    conn = get_conn()
    row = conn.execute("""SELECT COUNT(*) as n FROM medication_logs
        WHERE line_id=? AND status='taken' AND logged_at LIKE ?""",
        (line_id, f"{date_str}%")).fetchone()
    conn.close()
    return row["n"] > 0

def get_all_active_users():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM users WHERE name IS NOT NULL").fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Medication Logs ────────────────────────────────────────────────

def log_medication(line_id, status):
    conn = get_conn()
    conn.execute("INSERT INTO medication_logs (line_id, status, logged_at) VALUES (?,?,?)",
                 (line_id, status, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_recent_med_logs(line_id, days=7):
    since = (datetime.now() - timedelta(days=days)).isoformat()
    conn  = get_conn()
    rows  = conn.execute("""SELECT * FROM medication_logs
        WHERE line_id=? AND logged_at>=? ORDER BY logged_at DESC""",
        (line_id, since)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Health Logs ────────────────────────────────────────────────────

def save_health_log(line_id, value, log_type="general"):
    conn = get_conn()
    # Get log_type from user state if not provided
    user = conn.execute("SELECT health_log_type FROM users WHERE line_id=?",
                        (line_id,)).fetchone()
    if user and user["health_log_type"]:
        log_type = user["health_log_type"]
    conn.execute("INSERT INTO health_logs (line_id, log_type, value, logged_at) VALUES (?,?,?,?)",
                 (line_id, log_type, value, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_health_logs(line_id, limit=5):
    conn = get_conn()
    rows = conn.execute("""SELECT * FROM health_logs WHERE line_id=?
        ORDER BY logged_at DESC LIMIT ?""", (line_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Points ─────────────────────────────────────────────────────────

def get_points(line_id):
    conn = get_conn()
    row  = conn.execute("SELECT health_points FROM users WHERE line_id=?",
                        (line_id,)).fetchone()
    conn.close()
    return row["health_points"] if row else 0

def add_points(line_id, pts):
    conn = get_conn()
    conn.execute("UPDATE users SET health_points = health_points + ? WHERE line_id=?",
                 (pts, line_id))
    conn.commit()
    conn.close()

def redeem_points(line_id, points_used, discount_thb):
    conn = get_conn()
    conn.execute("UPDATE users SET health_points = health_points - ? WHERE line_id=?",
                 (points_used, line_id))
    conn.execute("INSERT INTO redemptions (line_id, points_used, discount_thb, redeemed_at) VALUES (?,?,?,?)",
                 (line_id, points_used, discount_thb, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_redemption_history(line_id):
    conn = get_conn()
    rows = conn.execute("""SELECT * FROM redemptions WHERE line_id=?
        ORDER BY redeemed_at DESC LIMIT 5""", (line_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Alerts ─────────────────────────────────────────────────────────

def save_alert(line_id, level, message, adr_description=None):
    conn = get_conn()
    conn.execute("""INSERT INTO alerts (line_id, level, message, adr_description, created_at)
        VALUES (?,?,?,?,?)""",
        (line_id, level, message, adr_description, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_recent_alerts(limit=20):
    conn = get_conn()
    rows = conn.execute("""
        SELECT a.*, u.name FROM alerts a
        LEFT JOIN users u ON a.line_id = u.line_id
        ORDER BY a.created_at DESC LIMIT ?""", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Refill ─────────────────────────────────────────────────────────

def get_refill_status(line_id):
    conn  = get_conn()
    row   = conn.execute("""SELECT * FROM refill_subscriptions
        WHERE line_id=? AND active=1 ORDER BY id DESC LIMIT 1""",
        (line_id,)).fetchone()
    conn.close()
    return dict(row) if row else None

# ── Dashboard ──────────────────────────────────────────────────────

def get_all_users_detail():
    conn  = get_conn()
    users = conn.execute("SELECT * FROM users WHERE name IS NOT NULL").fetchall()
    result = []
    for u in users:
        lid = u["line_id"]
        taken   = conn.execute("SELECT COUNT(*) as n FROM medication_logs WHERE line_id=? AND status='taken'",   (lid,)).fetchone()["n"]
        skipped = conn.execute("SELECT COUNT(*) as n FROM medication_logs WHERE line_id=? AND status='skipped'", (lid,)).fetchone()["n"]
        total   = taken + skipped
        adherence = round(taken / total * 100) if total > 0 else 0
        d = dict(u)
        d["taken_count"]   = taken
        d["skipped_count"] = skipped
        d["adherence"]     = adherence
        d["points"]        = u["health_points"]
        result.append(d)
    conn.close()
    return result
