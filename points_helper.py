# -*- coding: utf-8 -*-
# points_helper.py — standalone Jinja helper for per-game points labels
import os, sqlite3

def __points_meta(game_id: int):
    """Return (points_per_minute, min_seconds) with optional per-game overrides; safe on old schemas."""
    BASE = os.path.dirname(os.path.abspath(__file__))
    con = sqlite3.connect(os.path.join(BASE, 'survey.db'), timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    c = con.cursor()

    ppm, min_sec = 10, 30  # defaults

    # Global settings
    try:
        row = c.execute("SELECT value FROM settings WHERE key='points_per_minute'").fetchone()
        if row:
            v = row["value"] if isinstance(row, sqlite3.Row) else row[0]
            ppm = int(v)
    except Exception:
        pass
    try:
        row = c.execute("SELECT value FROM settings WHERE key='min_seconds_to_reward'").fetchone()
        if row:
            v = row["value"] if isinstance(row, sqlite3.Row) else row[0]
            min_sec = int(v)
    except Exception:
        pass

    # Per-game overrides (ignore if columns missing)
    try:
        g = c.execute("SELECT points_override, min_seconds_override FROM games WHERE id=?", (game_id,)).fetchone()
        if g:
            try:
                po = g["points_override"] if isinstance(g, sqlite3.Row) else g[0]
                if po and int(po) > 0:
                    ppm = int(po)
            except Exception:
                pass
            try:
                mo = g["min_seconds_override"] if isinstance(g, sqlite3.Row) else g[1]
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
    return f"{ppm} پۆینت/خولەک · {min_sec} چرکە کەمترین"

def register_points_helper(app):
    """
    Call this AFTER you create `app = Flask(__name__)`.
    It safely registers the Jinja global: game_points_label
    """
    app.jinja_env.globals["game_points_label"] = jinja_game_points_label
