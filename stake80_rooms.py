
# -*- coding: utf-8 -*-
"""
stake80_rooms.py — Room stake matches with 80/20 payout.

Endpoints (JSON):
POST /api/rooms/match/start   {game_id, room, stake}      -> {ok, match_id}
POST /api/rooms/match/join    {match_id}                  -> {ok}
POST /api/rooms/match/finish  {match_id, winner_user_id}  -> {ok, winner_points, admin_cut}

Rules:
- Each player pays `stake` points on start/join. Deducted from profiles.wallet_points.
- On finish: POT = stake * number_of_players.
  Winner gets floor(POT * 0.8).
  Admin wallet (settings['admin_wallet_points']) += POT - winner_points.
- All updates recorded in wallet_transactions (type: 'stake_pay', 'stake_win', 'stake_admin').
"""
import os, sqlite3, time
from flask import request, jsonify, session

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "survey.db")

def _db():
    con = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def _migrate():
    con = _db(); c = con.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS matches(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        game_id INTEGER NOT NULL,
        room TEXT NOT NULL,
        stake INTEGER NOT NULL,
        created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
        finished_at INTEGER
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS match_players(
        match_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        joined_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
        UNIQUE(match_id, user_id)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS app_settings(
        key TEXT PRIMARY KEY, value TEXT
    )""")
    # Ensure profiles + wallet
    try:
        c.execute("ALTER TABLE profiles ADD COLUMN wallet_points INTEGER DEFAULT 0")
    except Exception:
        pass
    c.execute("""CREATE TABLE IF NOT EXISTS wallet_transactions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        type TEXT,
        points INTEGER,
        note TEXT,
        created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
    )""")
    con.commit(); con.close()

def _get_setting(key, default="0"):
    con = _db(); c = con.cursor()
    row = c.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    con.close()
    return (row["value"] if row else str(default))

def _set_setting(key, value):
    con = _db(); c = con.cursor()
    if c.execute("SELECT 1 FROM app_settings WHERE key=?", (key,)).fetchone():
        c.execute("UPDATE app_settings SET value=? WHERE key=?", (str(value), key))
    else:
        c.execute("INSERT INTO app_settings(key,value) VALUES(?,?)", (key, str(value)))
    con.commit(); con.close()

def _wallet_get(uid:int)->int:
    con=_db(); c=con.cursor()
    row = c.execute("SELECT wallet_points FROM profiles WHERE user_id=?", (uid,)).fetchone()
    con.close()
    return int(row["wallet_points"]) if row and str(row["wallet_points"]).isdigit() else 0

def _wallet_add(uid:int, delta:int, note:str):
    con=_db(); c=con.cursor()
    # ensure row
    c.execute("UPDATE profiles SET wallet_points = COALESCE(wallet_points,0) + ? WHERE user_id=?", (delta, uid))
    if c.rowcount == 0:
        c.execute("INSERT OR IGNORE INTO profiles(user_id, wallet_points) VALUES (?, 0)", (uid,))
        c.execute("UPDATE profiles SET wallet_points = COALESCE(wallet_points,0) + ? WHERE user_id=?", (delta, uid))
    c.execute("INSERT INTO wallet_transactions(user_id, type, points, note) VALUES (?,?,?,?)",
              (uid, 'stake_'+('win' if delta>0 else 'pay'), delta, note))
    con.commit(); con.close()

def _admin_add(delta:int, note:str):
    cur = int(_get_setting('admin_wallet_points','0') or 0)
    _set_setting('admin_wallet_points', cur + int(delta))
    # also log to wallet_transactions with user_id NULL
    con=_db(); c=con.cursor()
    c.execute("INSERT INTO wallet_transactions(user_id, type, points, note) VALUES (NULL, 'stake_admin', ?, ?)",
              (int(delta), note))
    con.commit(); con.close()

def _require_user():
    uid = session.get('user_id') or session.get('uid') or 0
    if not uid: 
        return None, jsonify({'ok': False, 'error': 'not_authenticated'}), 401
    return int(uid), None, None

def _install_stake80(app):
    _migrate()

    @app.post('/api/rooms/match/start')
    def api_match_start():
        uid, resp, code = _require_user()
        if not uid: return resp, code
        data = request.get_json(silent=True) or {}
        try:
            game_id = int(data.get('game_id') or 0)
            stake   = int(data.get('stake') or 0)
            room    = (data.get('room') or '').strip() or 'public'
            assert game_id>0 and stake>0
        except Exception:
            return jsonify({'ok': False, 'error': 'bad_payload'}), 400
        # deduct stake
        cur = _wallet_get(uid)
        if cur < stake:
            return jsonify({'ok': False, 'error': 'insufficient_points', 'have': cur, 'need': stake}), 400
        _wallet_add(uid, -stake, f'stake_pay game:{game_id} room:{room}')
        # create match + join
        con=_db(); c=con.cursor()
        c.execute("INSERT INTO matches(game_id, room, stake) VALUES (?,?,?)", (game_id, room, stake))
        mid = c.lastrowid
        c.execute("INSERT OR IGNORE INTO match_players(match_id, user_id) VALUES (?,?)", (mid, uid))
        con.commit(); con.close()
        return jsonify({'ok': True, 'match_id': int(mid)})

    @app.post('/api/rooms/match/join')
    def api_match_join():
        uid, resp, code = _require_user()
        if not uid: return resp, code
        data = request.get_json(silent=True) or {}
        try:
            mid = int(data.get('match_id') or 0)
            assert mid>0
        except Exception:
            return jsonify({'ok': False, 'error': 'bad_payload'}), 400
        con=_db(); c=con.cursor()
        m = c.execute("SELECT stake, game_id, room FROM matches WHERE id=? AND finished_at IS NULL", (mid,)).fetchone()
        if not m: con.close(); return jsonify({'ok': False, 'error': 'not_found_or_finished'}), 404
        stake = int(m['stake']) if hasattr(m, 'keys') else int(m[0])
        game_id = m['game_id'] if hasattr(m, 'keys') else m[1]
        room = m['room'] if hasattr(m, 'keys') else m[2]
        cur = _wallet_get(uid)
        if cur < stake:
            con.close(); return jsonify({'ok': False, 'error': 'insufficient_points', 'have': cur, 'need': stake}), 400
        _wallet_add(uid, -stake, f'stake_pay game:{game_id} room:{room}')
        c.execute("INSERT OR IGNORE INTO match_players(match_id, user_id) VALUES (?,?)", (mid, uid))
        con.commit(); con.close()
        return jsonify({'ok': True})

    @app.post('/api/rooms/match/finish')
    def api_match_finish():
        uid, resp, code = _require_user()
        if not uid: return resp, code
        data = request.get_json(silent=True) or {}
        try:
            mid = int(data.get('match_id') or 0)
            winner = int(data.get('winner_user_id') or 0)
            assert mid>0 and winner>0
        except Exception:
            return jsonify({'ok': False, 'error': 'bad_payload'}), 400
        con=_db(); c=con.cursor()
        m = c.execute("SELECT stake, game_id, room FROM matches WHERE id=? AND finished_at IS NULL", (mid,)).fetchone()
        if not m: con.close(); return jsonify({'ok': False, 'error': 'not_found_or_finished'}), 404
        stake = int(m['stake']) if hasattr(m, 'keys') else int(m[0])
        game_id = m['game_id'] if hasattr(m, 'keys') else m[1]
        room = m['room'] if hasattr(m, 'keys') else m[2]
        # count players
        nrow = c.execute("SELECT COUNT(1) AS n FROM match_players WHERE match_id=?", (mid,)).fetchone()
        n = int(nrow['n']) if hasattr(nrow, 'keys') else int(nrow[0])
        pot = stake * n
        winner_points = int(pot * 0.8)  # floor
        admin_cut = pot - winner_points
        # settle
        _wallet_add(winner, +winner_points, f'stake_win game:{game_id} room:{room} match:{mid} pot:{pot}')
        _admin_add(admin_cut, f'stake_admin game:{game_id} room:{room} match:{mid} pot:{pot}')
        c.execute("UPDATE matches SET finished_at=strftime('%s','now') WHERE id=?", (mid,))
        con.commit(); con.close()
        return jsonify({'ok': True, 'winner_points': winner_points, 'admin_cut': admin_cut, 'pot': pot, 'players': n})
    return app

def install(app):
    return _install_stake80(app)
