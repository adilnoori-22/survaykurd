#!/usr/bin/env python3
# inspect_schema.py
# Usage: python inspect_schema.py --db "C:\Users\hp\Desktop\survey_app\survey.db"
import argparse, sqlite3

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    tables = ["payout_providers", "user_payout_methods", "payout_requests", "profiles", "wallet_transactions"]
    print("== PRAGMA table_info ==")
    for t in tables:
        try:
            cols = cur.execute(f"PRAGMA table_info({t})").fetchall()
            if not cols:
                print(f"- {t}: (missing table)")
            else:
                has_id = any(c["name"].lower() == "id" for c in cols)
                print(f"- {t}: columns={[c['name'] for c in cols]}  | has_id={has_id}")
        except sqlite3.OperationalError as e:
            print(f"- {t}: ERROR: {e}")

    # Try a minimal join like the page uses
    print("\n== quick select tests ==")
    try:
        cur.execute("SELECT id,name,kind,is_active FROM payout_providers LIMIT 1")
        print("providers: OK")
    except Exception as e:
        print("providers: FAIL ->", e)

    try:
        cur.execute("""SELECT m.id, m.provider_id, m.account_json, p.name, p.kind
                       FROM user_payout_methods m JOIN payout_providers p ON p.id=m.provider_id
                       LIMIT 1""")
        print("user_payout_methods join: OK")
    except Exception as e:
        print("user_payout_methods join: FAIL ->", e)

    try:
        cur.execute("SELECT id,user_id,status FROM payout_requests LIMIT 1")
        print("payout_requests: OK")
    except Exception as e:
        print("payout_requests: FAIL ->", e)

if __name__ == "__main__":
    main()
