#!/usr/bin/env python3
# migrate_payout_schema.py
# Usage: python migrate_payout_schema.py --db C:\Users\hp\Desktop\survey_app\survey.db
import argparse, sqlite3, sys, json, datetime, os, shutil

def connect(path):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    return con

def table_has_column(con, table, col):
    try:
        cols = con.execute(f"PRAGMA table_info({table})").fetchall()
        return any(c["name"].lower() == col.lower() for c in cols)
    except sqlite3.OperationalError:
        return False

def table_exists(con, table):
    r = con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return bool(r)

def safe_recreate_payout_providers(con):
    # ensure correct layout with 'id' INTEGER PRIMARY KEY AUTOINCREMENT
    need_recreate = (not table_exists(con, "payout_providers")) or (not table_has_column(con, "payout_providers", "id"))
    if not need_recreate:
        return False
    print("[migrate] Recreating payout_providers ...")
    con.execute("BEGIN")
    try:
        old_rows = []
        if table_exists(con, "payout_providers"):
            try:
                old_rows = con.execute("SELECT * FROM payout_providers").fetchall()
            except Exception:
                old_rows = []
        con.execute("""
CREATE TABLE IF NOT EXISTS __payout_providers_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind in ('bank','mobile')),
    is_active INTEGER DEFAULT 1,
    fields_json TEXT DEFAULT '{}'
)
""")
        # copy data if compatible columns exist
        for r in old_rows:
            name = r["name"] if "name" in r.keys() else None
            kind = r["kind"] if "kind" in r.keys() else "mobile"
            is_active = r["is_active"] if "is_active" in r.keys() else 1
            fields_json = r["fields_json"] if "fields_json" in r.keys() else "{}"
            if name:
                con.execute("INSERT INTO __payout_providers_new (name,kind,is_active,fields_json) VALUES (?,?,?,?)",
                            (name, kind, is_active, fields_json))
        # swap
        if table_exists(con, "payout_providers"):
            con.execute("DROP TABLE payout_providers")
        con.execute("ALTER TABLE __payout_providers_new RENAME TO payout_providers")
        con.commit()
        return True
    except Exception as e:
        con.rollback()
        print("[migrate][ERR] payout_providers:", e)
        raise

def safe_recreate_user_methods(con):
    need_recreate = (not table_exists(con, "user_payout_methods")) or (not table_has_column(con, "user_payout_methods", "id"))
    if not need_recreate:
        return False
    print("[migrate] Recreating user_payout_methods ...")
    con.execute("BEGIN")
    try:
        old_rows = []
        if table_exists(con, "user_payout_methods"):
            try:
                old_rows = con.execute("SELECT * FROM user_payout_methods").fetchall()
            except Exception:
                old_rows = []
        con.execute("""
CREATE TABLE IF NOT EXISTS __user_payout_methods_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    provider_id INTEGER NOT NULL,
    account_json TEXT NOT NULL,
    is_default INTEGER DEFAULT 1,
    status TEXT DEFAULT 'unverified',
    verified_at TEXT
)
""")
        for r in old_rows:
            user_id = r["user_id"] if "user_id" in r.keys() else None
            provider_id = r["provider_id"] if "provider_id" in r.keys() else None
            account_json = r["account_json"] if "account_json" in r.keys() else "{}"
            is_default = r["is_default"] if "is_default" in r.keys() else 1
            status = r["status"] if "status" in r.keys() else "unverified"
            verified_at = r["verified_at"] if "verified_at" in r.keys() else None
            if user_id and provider_id:
                con.execute("""INSERT INTO __user_payout_methods_new
                               (user_id,provider_id,account_json,is_default,status,verified_at)
                               VALUES (?,?,?,?,?,?)""",
                            (user_id, provider_id, account_json, is_default, status, verified_at))
        if table_exists(con, "user_payout_methods"):
            con.execute("DROP TABLE user_payout_methods")
        con.execute("ALTER TABLE __user_payout_methods_new RENAME TO user_payout_methods")
        con.commit()
        return True
    except Exception as e:
        con.rollback()
        print("[migrate][ERR] user_payout_methods:", e)
        raise

def ensure_payout_requests_columns(con):
    # make sure payout_requests has columns we read (id,user_id,method,provider,account,points,fee_points,status,created_at,processed_at)
    if not table_exists(con, "payout_requests"):
        print("[migrate] Creating payout_requests ...")
        con.execute("""
CREATE TABLE payout_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    method TEXT,
    provider TEXT,
    account TEXT,
    points INTEGER,
    fee_points INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    created_at TEXT,
    processed_at TEXT
)
""")
        con.commit()
        return True

    changed = False
    cols = [r["name"] for r in con.execute("PRAGMA table_info(payout_requests)")]
    needed = {
        "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
        "user_id": "INTEGER",
        "method": "TEXT",
        "provider": "TEXT",
        "account": "TEXT",
        "points": "INTEGER",
        "fee_points": "INTEGER DEFAULT 0",
        "status": "TEXT DEFAULT 'pending'",
        "created_at": "TEXT",
        "processed_at": "TEXT",
    }
    # SQLite cannot ALTER PRIMARY KEY easily; if id missing, recreate table
    if "id" not in cols:
        print("[migrate] Recreating payout_requests to add id ...")
        con.execute("BEGIN")
        try:
            old = con.execute("SELECT * FROM payout_requests").fetchall()
            con.execute("""
CREATE TABLE __payout_requests_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    method TEXT,
    provider TEXT,
    account TEXT,
    points INTEGER,
    fee_points INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',
    created_at TEXT,
    processed_at TEXT
)
""")
            # best-effort copy
            for r in old:
                values = {k: r[k] for k in r.keys() if k in needed and k != "id"}
                con.execute("""INSERT INTO __payout_requests_new
                               (user_id,method,provider,account,points,fee_points,status,created_at,processed_at)
                               VALUES (?,?,?,?,?,?,?,?,?)""",
                            (values.get("user_id"), values.get("method"), values.get("provider"),
                             values.get("account"), values.get("points"), values.get("fee_points",0),
                             values.get("status","pending"), values.get("created_at"), values.get("processed_at")))
            con.execute("DROP TABLE payout_requests")
            con.execute("ALTER TABLE __payout_requests_new RENAME TO payout_requests")
            con.commit()
            return True
        except Exception as e:
            con.rollback()
            print("[migrate][ERR] payout_requests recreate:", e)
            raise

    # Add any missing non-PK columns
    for col, decl in needed.items():
        if col in cols or col=="id":
            continue
        try:
            con.execute(f"ALTER TABLE payout_requests ADD COLUMN {col} {decl}")
            changed = True
        except Exception:
            pass
    if changed:
        con.commit()
    return changed

def seed_default_provider(con):
    # if table empty, add a mobile provider with Kurdish labels
    count = con.execute("SELECT COUNT(*) AS c FROM payout_providers").fetchone()["c"]
    if count == 0:
        print("[migrate] Seeding default mobile provider (Zain Cash) ...")
        fields = {
            "mobile": {"label":"ژمارەی مۆبایل","type":"tel","pattern":"^07\\d{9}$","required": True},
            "full_name": {"label":"ناوی تەواو","type":"text","required": True}
        }
        con.execute("INSERT INTO payout_providers(name,kind,is_active,fields_json) VALUES(?,?,?,?)",
                    ("Zain Cash", "mobile", 1, json.dumps(fields, ensure_ascii=False)))
        con.commit()

def backup_copy(db_path):
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{db_path}.bak_{ts}"
    shutil.copy2(db_path, bak)
    print(f"[backup] {bak}")
    return bak

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Path to your SQLite DB (survey.db)")
    args = ap.parse_args()
    dbp = args.db
    if not os.path.exists(dbp):
        print(f"[ERR] DB not found: {dbp}")
        sys.exit(1)

    backup_copy(dbp)

    con = connect(dbp)
    try:
        ch1 = safe_recreate_payout_providers(con)
        ch2 = safe_recreate_user_methods(con)
        ch3 = ensure_payout_requests_columns(con)
        seed_default_provider(con)
        print("[DONE] Migration finished.",
              f"providers_recreated={ch1}, methods_recreated={ch2}, payout_requests_changed={ch3}")
    finally:
        con.close()

if __name__ == "__main__":
    main()
