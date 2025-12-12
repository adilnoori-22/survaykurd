#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
One-time SQLite migration: ensure `pages` table has columns
(is_active, updated_at, template, path). Safe to re-run.

Usage (Windows):
  python migrate_pages_schema_v2.py --db "C:\Users\hp\Desktop\survey_app\survey.db"
  # یان:
  python migrate_pages_schema_v2.py --db C:/Users/hp/Desktop/survey_app/survey.db
"""

import argparse, sqlite3, os, sys, datetime

def has_column(cur, table, col):
    try:
        info = cur.execute(f"PRAGMA table_info({table})").fetchall()
        for r in info:
            try:
                if r["name"] == col: return True
            except Exception:
                if r[1] == col: return True
    except Exception:
        return False
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.path.join(os.getcwd(), "survey.db"))
    args = ap.parse_args()

    db_path = args.db
    print("[migrate] DB:", db_path)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    c = con.cursor()

    # 1) base table
    c.execute("""CREATE TABLE IF NOT EXISTS pages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        slug TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        content TEXT NOT NULL
    )""")

    # 2) add columns if missing
    added = []
    for col, ddl in [
        ("is_active", "INTEGER DEFAULT 1"),
        ("updated_at", "TEXT DEFAULT CURRENT_TIMESTAMP"),
        ("template", "TEXT DEFAULT 'page'"),
        ("path", "TEXT")
    ]:
        if not has_column(c, "pages", col):
            try:
                c.execute(f"ALTER TABLE pages ADD COLUMN {col} {ddl}")
                added.append(col)
            except Exception as e:
                print(f"[warn] add column {col} failed: {e}")

    # 3) defaults for existing rows
    try:
        if has_column(c, "pages", "is_active"):
            c.execute("UPDATE pages SET is_active=1 WHERE is_active IS NULL")
        if has_column(c, "pages", "updated_at"):
            now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("UPDATE pages SET updated_at=? WHERE updated_at IS NULL", (now,))
        if has_column(c, "pages", "template"):
            c.execute("UPDATE pages SET template='page' WHERE template IS NULL")
    except Exception as e:
        print("[warn] set defaults:", e)

    con.commit()
    con.close()
    print("[migrate] done. Added:", added or "nothing")

if __name__ == "__main__":
    main()
