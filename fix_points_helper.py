# -*- coding: utf-8 -*-
from pathlib import Path
import re, textwrap

APP = Path("app.py")
src = APP.read_text(encoding="utf-8")

# 1) Remove any early registration lines
src = re.sub(r"\n\s*app\.jinja_env\.globals\['game_points_label'\]\s*=\s*jinja_game_points_label\s*\n", "\n", src)

# 2) Ensure helper block exists (idempotent)
if "def jinja_game_points_label" not in src:
    helper = textwrap.dedent("""
    # --- Helpers to show game points in templates (AUTO PATCH) ---
    import os, sqlite3

    def __points_meta(game_id: int):
        BASE = os.path.dirname(os.path.abspath(__file__))
        con = sqlite3.connect(os.path.join(BASE, 'survey.db'), timeout=30, check_same_thread=False)
        con.row_factory = sqlite3.Row
        c = con.cursor()
        ppm, min_sec = 10, 30
        try:
            row = c.execute("SELECT value FROM settings WHERE key='points_per_minute'").fetchone()
            if row:
                v = row['value'] if hasattr(row, 'keys') else row[0]; ppm = int(v)
        except Exception: pass
        try:
            row = c.execute("SELECT value FROM settings WHERE key='min_seconds_to_reward'").fetchone()
            if row:
                v = row['value'] if hasattr(row, 'keys') else row[0]; min_sec = int(v)
        except Exception: pass
        try:
            g = c.execute("SELECT points_override, min_seconds_override FROM games WHERE id=?", (game_id,)).fetchone()
            if g:
                try:
                    po = g['points_override'] if hasattr(g,'keys') else g[0]
                    if po and int(po)>0: ppm = int(po)
                except Exception: pass
                try:
                    mo = g['min_seconds_override'] if hasattr(g,'keys') else g[1]
                    if mo and int(mo)>0: min_sec = int(mo)
                except Exception: pass
        except Exception: pass
        con.close()
        return ppm, min_sec

    def jinja_game_points_label(game_id):
        ppm, min_sec = __points_meta(int(game_id))
        return f"{ppm} پۆینت/خولەک · {min_sec} چرکە کەمترین"
    """)
    # insert after app = Flask(...)
    m = re.search(r"app\s*=\s*Flask\([^)]*\)", src)
    pos = m.end() if m else 0
    src = src[:pos] + "\n\n" + helper + "\n" + src[pos:]

# 3) Register AFTER definition (once)
if "game_points_label'] = jinja_game_points_label" not in src:
    m = re.search(r"def\s+jinja_game_points_label\s*\(", src)
    insert_after = src.find("\n", m.end())
    reg = "\n# Register helper after definition\napp.jinja_env.globals['game_points_label'] = jinja_game_points_label\n"
    src = src[:insert_after+1] + reg + src[insert_after+1:]

APP.write_text(src, encoding="utf-8")
print("[OK] Patched app.py")
