# -*- coding: utf-8 -*-
r"""
Fix `sqlite3.OperationalError: no such column: id` for table `pages`.

Usage (Windows CMD):
  cd C:\Users\hp\Desktop\survey_app
  python migrate_fix_pages_id.py

This will:
  - Open survey.db (same folder) unless DB_PATH env var is set.
  - If `pages.id` is missing, it will rebuild the table with an AUTOINCREMENT id,
    keep all data, and add columns (is_active, updated_at, template, path) with defaults.
"""
import os, sqlite3, sys

DB_PATH = os.environ.get("DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "survey.db")

def has_col(c, table, col):
    try:
        rows = c.execute(f"PRAGMA table_info({table})").fetchall()
        for r in rows:
            name = r[1] if not isinstance(r, sqlite3.Row) else r["name"]
            if name == col:
                return True
    except Exception:
        return False
    return False

def table_exists(c, name):
    r = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
    return bool(r)

def migrate():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    c = con.cursor()

    if not table_exists(c, "pages"):
        print("[info] pages table not found — creating fresh schema.")
        c.execute("""CREATE TABLE pages(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            template TEXT DEFAULT 'page',
            path TEXT
        )""")
        con.commit(); con.close()
        print("[ok] created empty pages table.")
        return

    if has_col(c, "pages", "id"):
        print("[ok] pages.id already exists — nothing to do.")
        con.close()
        return

    # Build dynamic copy SELECT based on existing columns
    cols = { (r[1] if not isinstance(r, sqlite3.Row) else r["name"]) for r in c.execute("PRAGMA table_info(pages)") }
    def H(x): return x in cols

    slug_expr     = "slug" if H("slug") else "NULL"
    title_expr    = "title" if H("title") else ( "slug" if H("slug") else "'Untitled'" )
    content_expr  = "content" if H("content") else "''"
    is_active_expr= "COALESCE(is_active,1)" if H("is_active") else "1"
    template_expr = "COALESCE(template,'page')" if H("template") else "'page'"
    path_expr     = "path" if H("path") else "NULL"
    updated_expr  = "COALESCE(updated_at, datetime('now'))" if H("updated_at") else "datetime('now')"

    try:
        c.execute("PRAGMA foreign_keys=OFF")
        c.execute("BEGIN IMMEDIATE")
        c.execute("""CREATE TABLE pages_new(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            template TEXT DEFAULT 'page',
            path TEXT
        )""")
        copy_sql = f"""
        INSERT INTO pages_new (slug,title,content,is_active,template,path,updated_at)
        SELECT {slug_expr}, {title_expr}, {content_expr}, {is_active_expr}, {template_expr}, {path_expr}, {updated_expr}
        FROM pages
        """
        c.execute(copy_sql)
        c.execute("DROP TABLE pages")
        c.execute("ALTER TABLE pages_new RENAME TO pages")
        c.execute("COMMIT")
        print("[ok] migrated `pages` → added AUTOINCREMENT id and normalized columns.")
    except Exception as e:
        try:
            c.execute("ROLLBACK")
        except Exception:
            pass
        print("[error] migration failed:", e)
        sys.exit(1)
    finally:
        c.execute("PRAGMA foreign_keys=ON")
        con.close()

if __name__ == "__main__":
    migrate()
    print("[done] You can now run: python app.py")
