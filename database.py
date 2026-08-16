import sqlite3
import os
from datetime import datetime, timedelta

DATABASE_URL = os.getenv("DATABASE_URL")
_using_postgres = False

def get_connection():
    global _using_postgres
    if DATABASE_URL:
        try:
            import psycopg2
            conn = psycopg2.connect(DATABASE_URL)
            _using_postgres = True
            return conn
        except Exception as e:
            print(f"Warning: PostgreSQL connection failed ({e}). Falling back to local SQLite keys.db...")
            _using_postgres = False
            return sqlite3.connect("keys.db")
    else:
        _using_postgres = False
        return sqlite3.connect("keys.db")

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    is_postgres = _using_postgres
    
    if is_postgres:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key VARCHAR(50) PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patch_files (
                id SERIAL PRIMARY KEY,
                file_name VARCHAR(255) NOT NULL,
                file_data BYTEA NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS license_keys (
                key VARCHAR(50) PRIMARY KEY,
                file_id INTEGER NOT NULL REFERENCES patch_files(id) ON DELETE CASCADE,
                duration_days INTEGER DEFAULT 3,
                max_devices INTEGER DEFAULT 1,
                is_disabled BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                activated_at TIMESTAMP,
                expires_at TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS active_users (
                id SERIAL PRIMARY KEY,
                key VARCHAR(50) NOT NULL REFERENCES license_keys(key) ON DELETE CASCADE,
                device_id VARCHAR(100) NOT NULL,
                activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS banned_users (
                device_id VARCHAR(100) PRIMARY KEY,
                reason VARCHAR(255) DEFAULT 'Banned by admin',
                banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS muted_users (
                device_id VARCHAR(100) PRIMARY KEY,
                muted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id SERIAL PRIMARY KEY,
                device_id VARCHAR(100) NOT NULL,
                sender VARCHAR(50) NOT NULL,
                message TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patch_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name TEXT NOT NULL,
                file_data BLOB NOT NULL,
                uploaded_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS license_keys (
                key TEXT PRIMARY KEY,
                file_id INTEGER NOT NULL,
                duration_days INTEGER DEFAULT 3,
                max_devices INTEGER DEFAULT 1,
                is_disabled INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                activated_at TEXT,
                expires_at TEXT,
                FOREIGN KEY (file_id) REFERENCES patch_files (id) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS active_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                device_id TEXT NOT NULL,
                activated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (key) REFERENCES license_keys (key) ON DELETE CASCADE
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS banned_users (
                device_id TEXT PRIMARY KEY,
                reason TEXT DEFAULT 'Banned by admin',
                banned_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS muted_users (
                device_id TEXT PRIMARY KEY,
                muted_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                message TEXT NOT NULL,
                sent_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
    conn.commit()
    conn.close()

def get_admin_password():
    conn = get_connection()
    cursor = conn.cursor()
    is_postgres = DATABASE_URL is not None
    try:
        if is_postgres:
            cursor.execute("SELECT value FROM settings WHERE key = %s", ("admin_password",))
        else:
            cursor.execute("SELECT value FROM settings WHERE key = ?", ("admin_password",))
        row = cursor.fetchone()
        conn.close()
        if row and row[0]:
            return row[0]
    except Exception:
        conn.close()
    return os.getenv("ADMIN_PASSWORD", "ADMINS194G19")

def set_admin_password(new_pass: str):
    conn = get_connection()
    cursor = conn.cursor()
    is_postgres = DATABASE_URL is not None
    if is_postgres:
        cursor.execute("INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", ("admin_password", new_pass))
    else:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", ("admin_password", new_pass))
    conn.commit()
    conn.close()

# --- FILE OPERATIONS ---

def save_file(file_name: str, file_data: bytes):
    conn = get_connection()
    cursor = conn.cursor()
    is_postgres = DATABASE_URL is not None
    now = datetime.utcnow()
    uploaded_at = now if is_postgres else now.isoformat()
    
    if is_postgres:
        cursor.execute(
            "INSERT INTO patch_files (file_name, file_data, uploaded_at) VALUES (%s, %s, %s) RETURNING id",
            (file_name, file_data, uploaded_at)
        )
        file_id = cursor.fetchone()[0]
    else:
        cursor.execute(
            "INSERT INTO patch_files (file_name, file_data, uploaded_at) VALUES (?, ?, ?)",
            (file_name, file_data, uploaded_at)
        )
        file_id = cursor.lastrowid
        
    conn.commit()
    conn.close()
    return file_id

def get_all_files():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, file_name, uploaded_at FROM patch_files ORDER BY uploaded_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_file_by_id(file_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    is_postgres = DATABASE_URL is not None
    if is_postgres:
        cursor.execute("SELECT file_name, file_data FROM patch_files WHERE id = %s", (file_id,))
    else:
        cursor.execute("SELECT file_name, file_data FROM patch_files WHERE id = ?", (file_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def delete_file(file_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    is_postgres = DATABASE_URL is not None
    if is_postgres:
        cursor.execute("DELETE FROM patch_files WHERE id = %s", (file_id,))
    else:
        cursor.execute("DELETE FROM patch_files WHERE id = ?", (file_id,))
    conn.commit()
    conn.close()

# --- LICENSE KEY OPERATIONS ---

def create_key(key: str, file_id: int, duration_days: int = 3, max_devices: int = 1):
    conn = get_connection()
    cursor = conn.cursor()
    is_postgres = DATABASE_URL is not None
    now = datetime.utcnow()
    created_at = now if is_postgres else now.isoformat()
    
    if is_postgres:
        cursor.execute(
            "INSERT INTO license_keys (key, file_id, duration_days, max_devices, created_at) VALUES (%s, %s, %s, %s, %s)",
            (key, file_id, duration_days, max_devices, created_at)
        )
    else:
        cursor.execute(
            "INSERT INTO license_keys (key, file_id, duration_days, max_devices, created_at) VALUES (?, ?, ?, ?, ?)",
            (key, file_id, duration_days, max_devices, created_at)
        )
    conn.commit()
    conn.close()

def get_all_keys():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT k.key, k.file_id, k.duration_days, k.max_devices, k.created_at, k.activated_at, k.expires_at, f.file_name,
               (SELECT COUNT(*) FROM active_users u WHERE u.key = k.key) as active_devices_count,
               k.is_disabled
        FROM license_keys k
        LEFT JOIN patch_files f ON k.file_id = f.id
        ORDER BY k.created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def is_device_banned(device_id: str) -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    is_postgres = DATABASE_URL is not None
    if is_postgres:
        cursor.execute("SELECT device_id FROM banned_users WHERE device_id = %s", (device_id,))
    else:
        cursor.execute("SELECT device_id FROM banned_users WHERE device_id = ?", (device_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def ban_device(device_id: str, reason: str = "Banned by admin"):
    conn = get_connection()
    cursor = conn.cursor()
    is_postgres = DATABASE_URL is not None
    now = datetime.utcnow()
    banned_at = now if is_postgres else now.isoformat()
    if is_postgres:
        cursor.execute("INSERT INTO banned_users (device_id, reason, banned_at) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING", (device_id, reason, banned_at))
    else:
        cursor.execute("INSERT OR IGNORE INTO banned_users (device_id, reason, banned_at) VALUES (?, ?, ?)", (device_id, reason, banned_at))
    conn.commit()
    conn.close()

def unban_device(device_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    is_postgres = DATABASE_URL is not None
    if is_postgres:
        cursor.execute("DELETE FROM banned_users WHERE device_id = %s", (device_id,))
    else:
        cursor.execute("DELETE FROM banned_users WHERE device_id = ?", (device_id,))
    conn.commit()
    conn.close()

def mute_device(device_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    is_postgres = DATABASE_URL is not None
    now = datetime.utcnow()
    muted_at = now if is_postgres else now.isoformat()
    if is_postgres:
        cursor.execute("INSERT INTO muted_users (device_id, muted_at) VALUES (%s, %s) ON CONFLICT DO NOTHING", (device_id, muted_at))
    else:
        cursor.execute("INSERT OR IGNORE INTO muted_users (device_id, muted_at) VALUES (?, ?)", (device_id, muted_at))
    conn.commit()
    conn.close()

def unmute_device(device_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    is_postgres = DATABASE_URL is not None
    if is_postgres:
        cursor.execute("DELETE FROM muted_users WHERE device_id = %s", (device_id,))
    else:
        cursor.execute("DELETE FROM muted_users WHERE device_id = ?", (device_id,))
    conn.commit()
    conn.close()

def set_key_disabled(key: str, disabled: bool):
    conn = get_connection()
    cursor = conn.cursor()
    is_postgres = DATABASE_URL is not None
    val = disabled if is_postgres else (1 if disabled else 0)
    if is_postgres:
        cursor.execute("UPDATE license_keys SET is_disabled = %s WHERE key = %s", (val, key))
    else:
        cursor.execute("UPDATE license_keys SET is_disabled = ? WHERE key = ?", (val, key))
    conn.commit()
    conn.close()

def add_days_to_key(key: str, extra_days: int):
    conn = get_connection()
    cursor = conn.cursor()
    is_postgres = DATABASE_URL is not None
    if is_postgres:
        cursor.execute("SELECT activated_at, expires_at, duration_days FROM license_keys WHERE key = %s", (key,))
    else:
        cursor.execute("SELECT activated_at, expires_at, duration_days FROM license_keys WHERE key = ?", (key,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return
    act, exp, dur = row
    new_dur = (dur or 0) + extra_days
    
    if exp:
        try:
            exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00").split(".")[0])
        except Exception:
            exp_dt = datetime.strptime(str(exp).split(".")[0], "%Y-%m-%d %H:%M:%S")
        new_exp = exp_dt + timedelta(days=extra_days)
        new_exp_str = new_exp if is_postgres else new_exp.isoformat()
        if is_postgres:
            cursor.execute("UPDATE license_keys SET duration_days = %s, expires_at = %s WHERE key = %s", (new_dur, new_exp_str, key))
        else:
            cursor.execute("UPDATE license_keys SET duration_days = ?, expires_at = ? WHERE key = ?", (new_dur, new_exp_str, key))
    else:
        if is_postgres:
            cursor.execute("UPDATE license_keys SET duration_days = %s WHERE key = %s", (new_dur, key))
        else:
            cursor.execute("UPDATE license_keys SET duration_days = ? WHERE key = ?", (new_dur, key))
    conn.commit()
    conn.close()

def verify_key(key: str, device_id: str):
    if is_device_banned(device_id):
        return {"status": "banned", "message": "Device is banned"}

    if key == "ADMINS194G19" or key == get_admin_password():
        return {
            "status": "admin_success",
            "role": "admin",
            "expires_at": "2099-12-31T23:59:59Z",
            "file_id": 1,
            "message": "Welcome Admin"
        }

    conn = get_connection()
    cursor = conn.cursor()
    is_postgres = DATABASE_URL is not None
    
    if is_postgres:
        cursor.execute("SELECT file_id, duration_days, max_devices, activated_at, expires_at, is_disabled FROM license_keys WHERE key = %s", (key,))
    else:
        cursor.execute("SELECT file_id, duration_days, max_devices, activated_at, expires_at, is_disabled FROM license_keys WHERE key = ?", (key,))
        
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"status": "invalid", "message": "Key not found"}
        
    file_id, duration_days, max_devices, db_activated_at, db_expires_at, is_disabled = row

    if is_disabled:
        conn.close()
        return {"status": "disabled", "message": "Key has been disabled by admin"}

    now = datetime.utcnow()
    
    def parse_date(val):
        if not val:
            return None
        if isinstance(val, datetime):
            return val
        try:
            return datetime.fromisoformat(val)
        except Exception:
            return datetime.strptime(val.split('.')[0], "%Y-%m-%d %H:%M:%S")
            
    activated_at_dt = parse_date(db_activated_at)
    expires_at_dt = parse_date(db_expires_at)
    
    if is_postgres:
        cursor.execute("SELECT device_id FROM active_users WHERE key = %s", (key,))
    else:
        cursor.execute("SELECT device_id FROM active_users WHERE key = ?", (key,))
    registered_devices = [r[0] for r in cursor.fetchall()]
    
    if device_id in registered_devices:
        if expires_at_dt and now > expires_at_dt:
            conn.close()
            return {"status": "expired", "message": "Key has expired"}
        conn.close()
        return {
            "status": "success", 
            "expires_at": expires_at_dt.isoformat() if expires_at_dt else None,
            "file_id": file_id
        }
        
    if len(registered_devices) < max_devices:
        activated_at_str = now if is_postgres else now.isoformat()
        
        if not activated_at_dt:
            expires_at_dt = now + timedelta(days=duration_days)
            expires_at_str = expires_at_dt if is_postgres else expires_at_dt.isoformat()
            
            if is_postgres:
                cursor.execute(
                    "UPDATE license_keys SET activated_at = %s, expires_at = %s WHERE key = %s",
                    (activated_at_str, expires_at_str, key)
                )
            else:
                cursor.execute(
                    "UPDATE license_keys SET activated_at = ?, expires_at = ? WHERE key = ?",
                    (activated_at_str, expires_at_str, key)
                )
            
        if is_postgres:
            cursor.execute(
                "INSERT INTO active_users (key, device_id, activated_at) VALUES (%s, %s, %s)",
                (key, device_id, activated_at_str)
            )
        else:
            cursor.execute(
                "INSERT INTO active_users (key, device_id, activated_at) VALUES (?, ?, ?)",
                (key, device_id, activated_at_str)
            )
            
        conn.commit()
        conn.close()
        
        target_expiry = expires_at_dt or (now + timedelta(days=duration_days))
        return {
            "status": "success", 
            "expires_at": target_expiry.isoformat(),
            "file_id": file_id,
            "role": "user"
        }
    else:
        conn.close()
        return {"status": "device_mismatch", "message": "Key is bound to another device"}

def delete_key(key: str):
    conn = get_connection()
    cursor = conn.cursor()
    is_postgres = DATABASE_URL is not None
    if is_postgres:
        cursor.execute("DELETE FROM license_keys WHERE key = %s", (key,))
    else:
        cursor.execute("DELETE FROM license_keys WHERE key = ?", (key,))
    conn.commit()
    conn.close()

def get_all_users():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id, u.key, u.device_id, u.activated_at, k.expires_at, f.file_name,
               (SELECT COUNT(*) FROM banned_users b WHERE b.device_id = u.device_id) as is_banned,
               (SELECT COUNT(*) FROM muted_users m WHERE m.device_id = u.device_id) as is_muted
        FROM active_users u
        LEFT JOIN license_keys k ON u.key = k.key
        LEFT JOIN patch_files f ON k.file_id = f.id
        ORDER BY u.activated_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def send_chat_message(device_id: str, sender: str, message: str):
    conn = get_connection()
    cursor = conn.cursor()
    is_postgres = DATABASE_URL is not None
    now = datetime.utcnow()
    sent_at = now if is_postgres else now.isoformat()
    if is_postgres:
        cursor.execute("INSERT INTO chat_messages (device_id, sender, message, sent_at) VALUES (%s, %s, %s, %s)", (device_id, sender, message, sent_at))
    else:
        cursor.execute("INSERT INTO chat_messages (device_id, sender, message, sent_at) VALUES (?, ?, ?, ?)", (device_id, sender, message, sent_at))
    conn.commit()
    conn.close()

def get_chat_messages(device_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    is_postgres = DATABASE_URL is not None
    if is_postgres:
        cursor.execute("SELECT id, device_id, sender, message, sent_at FROM chat_messages WHERE device_id = %s ORDER BY id ASC", (device_id,))
    else:
        cursor.execute("SELECT id, device_id, sender, message, sent_at FROM chat_messages WHERE device_id = ? ORDER BY id ASC", (device_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_db_stats():
    import time
    start_time = time.time()
    conn = get_connection()
    cursor = conn.cursor()
    is_postgres = _using_postgres
    
    cursor.execute("SELECT 1")
    cursor.fetchone()
    ping_ms = round((time.time() - start_time) * 1000, 2)
    
    db_size_bytes = 0
    if is_postgres:
        try:
            cursor.execute("SELECT pg_database_size(current_database())")
            row = cursor.fetchone()
            if row:
                db_size_bytes = row[0]
        except Exception:
            db_size_bytes = 1024 * 1024
    else:
        if os.path.exists("keys.db"):
            db_size_bytes = os.path.getsize("keys.db")

    conn.close()
    db_size_mb = round(db_size_bytes / (1024 * 1024), 2)
    max_mb = 500.0
    used_percent = round((db_size_mb / max_mb) * 100, 1)

    return {
        "db_type": "PostgreSQL (Supabase)" if is_postgres else "SQLite",
        "ping_ms": ping_ms,
        "size_mb": db_size_mb,
        "max_mb": max_mb,
        "used_percent": used_percent
    }
