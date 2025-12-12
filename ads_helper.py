# -*- coding: utf-8 -*-
import os, sqlite3, random

def _db_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "survey.db")

def _connect():
    con = sqlite3.connect(_db_path(), timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def ads_migrate():
    con = _connect(); c = con.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS ads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT,
        image_url TEXT,
        click_url TEXT,
        is_active INTEGER DEFAULT 1,
        placement TEXT,               -- 'game_start' | 'level_complete'
        game_id INTEGER NOT NULL,     -- per-game only
        level_from INTEGER,
        level_to INTEGER,
        weight INTEGER DEFAULT 1
    )""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ads_game_place ON ads(game_id, placement)")
    con.commit(); con.close()

def ad_pick(game_id, placement, level=None):
    ads_migrate()
    con = _connect(); c = con.cursor()
    where = ["COALESCE(is_active,1)=1", "game_id = ?", "placement = ?"]
    params = [int(game_id), placement]
    if level is not None:
        where.append("(level_from IS NULL OR level_from <= ?)")
        where.append("(level_to IS NULL OR level_to >= ?)")
        params += [int(level), int(level)]
    sql = "SELECT id,title,image_url,click_url,COALESCE(weight,1) AS weight FROM ads WHERE " + " AND ".join(where)
    rows = c.execute(sql, params).fetchall()
    con.close()
    if not rows:
        return None
    bag = []
    for r in rows:
        w = int((r["weight"] if isinstance(r, sqlite3.Row) else r[4]) or 1)
        bag += [r] * (w if w > 0 else 1)
    pick = random.choice(bag)
    return dict(pick)

def ad_get_start(game_id):
    return ad_pick(game_id, "game_start", None)

def ads_admin_list(game_id):
    ads_migrate()
    con = _connect(); c = con.cursor()
    rows = c.execute("SELECT * FROM ads WHERE game_id=? ORDER BY placement, id DESC", (int(game_id),)).fetchall()
    con.close()
    return rows

def ads_admin_create(game_id, title, image_url, click_url, placement, level_from, level_to, weight, is_active):
    ads_migrate()
    con = _connect(); c = con.cursor()
    c.execute("""INSERT INTO ads(title,image_url,click_url,is_active,placement,game_id,level_from,level_to,weight)
                 VALUES(?,?,?,?,?,?,?,?,?)""",
              (title or "", image_url or "", click_url or "", int(is_active or 1),
               placement or "game_start", int(game_id),
               int(level_from) if (str(level_from).isdigit()) else None,
               int(level_to) if (str(level_to).isdigit()) else None,
               int(weight) if (str(weight).isdigit()) else 1))
    con.commit(); con.close()

def ads_admin_toggle(game_id, ad_id):
    con = _connect(); c = con.cursor()
    c.execute("UPDATE ads SET is_active = CASE COALESCE(is_active,1) WHEN 1 THEN 0 ELSE 1 END WHERE id=? AND game_id=?", (int(ad_id), int(game_id)))
    con.commit(); con.close()

def ads_admin_delete(game_id, ad_id):
    con = _connect(); c = con.cursor()
    c.execute("DELETE FROM ads WHERE id=? AND game_id=?", (int(ad_id), int(game_id)))
    con.commit(); con.close()

def credit_points_for_ad(user_id, game_id, ad_id, default_points=2):
    con = _connect(); c = con.cursor()
    try:
        row = c.execute("SELECT value FROM app_settings WHERE key='pts_ad_view'").fetchone()
        pts = int(row["value"]) if row and str(row["value"]).isdigit() else default_points
    except Exception:
        pts = default_points
    try:
        c.execute("ALTER TABLE profiles ADD COLUMN wallet_points INTEGER DEFAULT 0")
        con.commit()
    except Exception:
        pass
    c.execute("UPDATE profiles SET wallet_points = COALESCE(wallet_points,0) + ? WHERE user_id=?", (pts, int(user_id)))
    c.execute("INSERT INTO wallet_transactions(user_id,type,points,note) VALUES (?,?,?,?)",
              (int(user_id), "earn", pts, f"ad:{int(ad_id)} game:{int(game_id)}"))
    con.commit(); con.close()
    return pts
