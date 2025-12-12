# -*- coding: utf-8 -*-
r"""
Usage:
    cd C:\Users\hp\Desktop\survey_app
    python fix_game_points_helper_v2.py
Then:
    python app.py
This script:
- Removes any existing definitions of __points_meta / jinja_game_points_label
- Removes any early/duplicate registrations of game_points_label
- Appends a clean helper block at the END of app.py (top-level, correct indentation)
"""
from pathlib import Path
import re, sys

APP = Path("app.py")
if not APP.exists():
    print("ERROR: app.py not found in current folder.")
    sys.exit(1)

src = APP.read_text(encoding="utf-8", errors="ignore")

# 1) Remove any registrations anywhere
src = re.sub(
    r"\n\s*app\.jinja_env\.globals\['game_points_label'\]\s*=\s*jinja_game_points_label\s*(#.*)?\n",
    "\n",
    src,
    flags=re.M
)

# 2) Remove any existing helper defs (top-level) to avoid duplicates
def remove_def(name, text):
    # match: def name(...):\n [indented block]*
    pattern = re.compile(r"(?m)^\s*def\s+" + re.escape(name) + r"\s*\([^\)]*\)\s*:\s*\n(?:[ \t].*\n)*")
    return re.sub(pattern, "", text)

src = remove_def("__points_meta", src)
src = remove_def("jinja_game_points_label", src)

# 3) Append a clean helper block at EOF (ensure two leading newlines)
helper = """
\n\n# === Per-game points helper (APPENDED) ===
import os, sqlite3

def __points_meta(game_id: int):
    \"\"\"Return (points_per_minute, min_seconds) with optional per-game overrides.\"\"\"
    BASE = os.path.dirname(os.path.abspath(__file__))
    con = sqlite3.connect(os.path.join(BASE, 'survey.db'), timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    c = con.cursor()

    ppm, min_sec = 10, 30  # defaults

    # Global settings
    try:
        row = c.execute(\"SELECT value FROM settings WHERE key='points_per_minute'\").fetchone()
        if row:
            v = row['value'] if hasattr(row, 'keys') else row[0]
            ppm = int(v)
    except Exception:
        pass
    try:
        row = c.execute(\"SELECT value FROM settings WHERE key='min_seconds_to_reward'\").fetchone()
        if row:
            v = row['value'] if hasattr(row, 'keys') else row[0]
            min_sec = int(v)
    except Exception:
        pass

    # Per-game overrides (ignore if columns missing)
    try:
        g = c.execute(\"SELECT points_override, min_seconds_override FROM games WHERE id=?\", (game_id,)).fetchone()
        if g:
            try:
                po = g['points_override'] if hasattr(g, 'keys') else g[0]
                if po and int(po) > 0:
                    ppm = int(po)
            except Exception:
                pass
            try:
                mo = g['min_seconds_override'] if hasattr(g, 'keys') else g[1]
                if mo and int(mo) > 0:
                    min_sec = int(mo)
            except Exception:
                pass
    except Exception:
        pass

    con.close()
    return ppm, min_sec

def jinja_game_points_label(game_id):
    ppm, min_sec = __points_meta(int(game_id))
    return f\"{ppm} پۆینت/خولەک · {min_sec} چرکە کەمترین\"

# Register AFTER definition (safe: at EOF)
app.jinja_env.globals['game_points_label'] = jinja_game_points_label
# === End helper ===
"""

APP.write_text(src.rstrip() + helper, encoding="utf-8")
print("[OK] Helper appended at EOF. Now run: python app.py")
