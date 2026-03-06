import sqlite3
from datetime import datetime

DB_NAME = "osocare.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Users table — เพิ่ม adr_mode และ awaiting_med
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            line_id TEXT PRIMARY KEY,
            name TEXT,
            med_name TEXT DEFAULT 'ยาตามใบสั่ง',
            points INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            registered_at TEXT,
            adr_mode INTEGER DEFAULT 0,
            awaiting_med INTEGER DEFAULT 0
        )
    """)

    # Medication logs
    c.execute("""
        CREATE TABLE IF NOT EXISTS medication_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            line_id TEXT,
            status TEXT,
            logged_at TEXT
        )
    """)

    # Alerts — เพิ่ม adr_description
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            line_id TEXT,
            level TEXT,
            message TEXT,
            adr_description TEXT,
            created_at TEXT,
            resolved INTEGER DEFAULT 0
        )
    """)

    # Redemptions — ประวัติการแลกแต้ม
    c.execute("""
        CREATE TABLE IF NOT EXISTS redemptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            line_id TEXT,
            points_used INTEGER,
            discount_thb INTEGER,
            redeemed_at TEXT
        )
    """)

    # Migration — เพิ่ม columns ถ้ายังไม่มี (สำหรับ DB เก่า)
    for col, definition in [
        ("adr_mode", "INTEGER DEFAULT 0"),
        ("awaiting_med", "INTEGER DEFAULT 0")
    ]:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
        except Exception:
            pass

    for col, definition in [
        ("adr_description", "TEXT"),
        ("resolved", "INTEGER DEFAULT 0")
    ]:
        try:
            c.execute(f"ALTER TABLE alerts ADD COLUMN {col} {definition}")
        except Exception:
            pass

    conn.commit()
    conn.close()

# ───────────────────────────── USER ─────────────────────────────

def save_user(line_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO users (line_id, registered_at)
        VALUES (?, ?)
    """, (line_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_user(line_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE line_id = ?", (line_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return {
            "line_id": row[0],
            "name": row[1],
            "med_name": row[2],
            "points": row[3],
            "status": row[4],
            "registered_at": row[5],
            "adr_mode": row[6] if len(row) > 6 else 0,
            "awaiting_med": row[7] if len(row) > 7 else 0
        }
    return None

def get_all_active_users():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT line_id, name, med_name FROM users WHERE status = 'active'")
    rows = c.fetchall()
    conn.close()
    return [{"line_id": r[0], "name": r[1], "med_name": r[2]} for r in rows]

def get_all_users_detail():
    """สำหรับ Dashboard เภสัชกร"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT u.line_id, u.name, u.med_name, u.points, u.status, u.registered_at,
               COUNT(CASE WHEN ml.status = 'taken' THEN 1 END) as taken_count,
               COUNT(CASE WHEN ml.status = 'skipped' THEN 1 END) as skipped_count,
               COUNT(ml.id) as total_logs
        FROM users u
        LEFT JOIN medication_logs ml ON u.line_id = ml.line_id
        GROUP BY u.line_id
        ORDER BY u.registered_at DESC
    """)
    rows = c.fetchall()
    conn.close()
    return [{
        "line_id": r[0],
        "name": r[1] or "ไม่ระบุ",
        "med_name": r[2] or "ไม่ระบุ",
        "points": r[3],
        "status": r[4],
        "registered_at": r[5],
        "taken_count": r[6],
        "skipped_count": r[7],
        "total_logs": r[8],
        "adherence": round(r[6] / r[8] * 100) if r[8] > 0 else 0
    } for r in rows]

def update_user_name(line_id, name):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET name = ? WHERE line_id = ?", (name, line_id))
    conn.commit()
    conn.close()

def update_user_med(line_id, med_name):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET med_name = ?, awaiting_med = 0 WHERE line_id = ?",
              (med_name, line_id))
    conn.commit()
    conn.close()

def set_awaiting_med(line_id, value=1):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET awaiting_med = ? WHERE line_id = ?", (value, line_id))
    conn.commit()
    conn.close()

def set_adr_mode(line_id, value=1):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET adr_mode = ? WHERE line_id = ?", (value, line_id))
    conn.commit()
    conn.close()

# ─────────────────────────── MEDICATION ─────────────────────────

def log_medication(line_id, status):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        INSERT INTO medication_logs (line_id, status, logged_at)
        VALUES (?, ?, ?)
    """, (line_id, status, datetime.now().isoformat()))
    conn.commit()
    conn.close()

# ─────────────────────────── POINTS ─────────────────────────────

def add_points(line_id, pts):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET points = points + ? WHERE line_id = ?", (pts, line_id))
    conn.commit()
    conn.close()

def get_points(line_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT points FROM users WHERE line_id = ?", (line_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def redeem_points(line_id, points_used, discount_thb):
    """หักแต้มและบันทึกการแลก"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET points = points - ? WHERE line_id = ?",
              (points_used, line_id))
    c.execute("""
        INSERT INTO redemptions (line_id, points_used, discount_thb, redeemed_at)
        VALUES (?, ?, ?, ?)
    """, (line_id, points_used, discount_thb, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_redemption_history(line_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT points_used, discount_thb, redeemed_at
        FROM redemptions WHERE line_id = ?
        ORDER BY redeemed_at DESC LIMIT 5
    """, (line_id,))
    rows = c.fetchall()
    conn.close()
    return [{"points_used": r[0], "discount_thb": r[1], "redeemed_at": r[2]} for r in rows]

# ─────────────────────────── ALERTS ─────────────────────────────

def save_alert(line_id, level, message, adr_description=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        INSERT INTO alerts (line_id, level, message, adr_description, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (line_id, level, message, adr_description, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_recent_alerts(limit=20):
    """สำหรับ Dashboard เภสัชกร"""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        SELECT a.id, u.name, a.level, a.message, a.adr_description, a.created_at, a.resolved
        FROM alerts a
        LEFT JOIN users u ON a.line_id = u.line_id
        ORDER BY a.created_at DESC LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return [{
        "id": r[0],
        "name": r[1] or "ไม่ระบุ",
        "level": r[2],
        "message": r[3],
        "adr_description": r[4],
        "created_at": r[5],
        "resolved": r[6]
    } for r in rows]
