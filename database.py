import sqlite3
from datetime import datetime

DB_NAME = "osocare.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            line_id TEXT PRIMARY KEY,
            name TEXT,
            med_name TEXT,
            med_time TEXT DEFAULT '08:00',
            points INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            registered_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS medication_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            line_id TEXT,
            status TEXT,
            logged_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            line_id TEXT,
            level TEXT,
            message TEXT,
            created_at TEXT,
            resolved INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def save_user(line_id, name="", med_name="ยาตามใบสั่ง"):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO users (line_id, name, med_name, registered_at)
        VALUES (?, ?, ?, ?)
    """, (line_id, name, med_name, datetime.now().isoformat()))
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
            "line_id": row[0], "name": row[1],
            "med_name": row[2], "med_time": row[3],
            "points": row[4], "status": row[5]
        }
    return None

def get_all_active_users():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE status = 'active'")
    rows = c.fetchall()
    conn.close()
    return [{"line_id": r[0], "name": r[1], "med_name": r[2]} for r in rows]

def log_medication(line_id, status):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        INSERT INTO medication_logs (line_id, status, logged_at)
        VALUES (?, ?, ?)
    """, (line_id, status, datetime.now().isoformat()))
    conn.commit()
    conn.close()

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

def save_alert(line_id, level, message):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        INSERT INTO alerts (line_id, level, message, created_at)
        VALUES (?, ?, ?, ?)
    """, (line_id, level, message, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def update_user_name(line_id, name):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE users SET name = ? WHERE line_id = ?", (name, line_id))
    conn.commit()
    conn.close()
