
# db_wallet_migration.py
# Usage (run inside your project folder):
#   python db_wallet_migration.py
#
# What it does:
#   - Opens ./survey.db
#   - Ensures table 'users' exists
#   - Adds column users.wallet_points INTEGER DEFAULT 0 if missing
#   - Backfills NULLs to 0
#   - Ensures settings table and seeds two keys if missing:
#       points_per_minute=10, min_seconds_to_reward=30

import os, sqlite3, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "survey.db")

def connect():
    con = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def col_exists(info_rows, name):
    for r in info_rows:
        # r: cid, name, type, notnull, dflt_value, pk
        if (isinstance(r, tuple) and len(r)>1 and r[1]==name) or (hasattr(r, 'keys') and r['name']==name):
            return True
    return False

def main():
    if not os.path.exists(DB_PATH):
        print(f"[WARN] DB not found at {DB_PATH} — nothing to migrate.")
        sys.exit(0)

    con = connect(); c = con.cursor()

    # 1) Ensure users table exists (minimal schema)
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, wallet_points INTEGER DEFAULT 0, created_at TEXT)')
    con.commit()

    # 2) Ensure wallet_points column exists
    info = c.execute("PRAGMA table_info('users')").fetchall()
    if not col_exists(info, "wallet_points"):
        print("[MIGRATE] adding users.wallet_points ...")
        c.execute("ALTER TABLE users ADD COLUMN wallet_points INTEGER DEFAULT 0")
        con.commit()
        # Backfill nulls just in case
        c.execute("UPDATE users SET wallet_points=0 WHERE wallet_points IS NULL")
        con.commit()
    else:
        print("[OK] users.wallet_points already exists.")

    # 3) Ensure settings table + defaults
    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
    con.commit()

    def ensure_setting(k, v):
        row = c.execute("SELECT 1 FROM settings WHERE key=?", (k,)).fetchone()
        if not row:
            c.execute("INSERT INTO settings(key,value) VALUES(?,?)", (k, str(v)))
            con.commit()
            print(f"[SEED] settings[{k}] = {v}")
        else:
            print(f"[OK] settings[{k}] exists.")

    ensure_setting("points_per_minute", 10)
    ensure_setting("min_seconds_to_reward", 30)

    con.close()
    print("[DONE] Migration completed successfully.")

if __name__ == '__main__':
    main()
