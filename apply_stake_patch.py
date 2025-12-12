# -*- coding: utf-8 -*-
"""
apply_stake_patch.py

Run inside your project folder (where app.py lives):
    python apply_stake_patch.py
Then restart:
    python app.py

Adds "stake/bet" matches so members can:
- Create a match in a room with an entry stake (points).
- Join the match (stake deducted).
- Report the winner; pot is transferred to winner's wallet.
- See a simple leaderboard per room/game.
It also extends portal UI to expose these actions.
"""

import os, re, sqlite3, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app.py"
if not APP.exists():
    raise SystemExit("ERROR: app.py not found here.")

# Backup
BAK = ROOT / "app.py.bak_stake"
shutil.copyfile(APP, BAK)

code = APP.read_text(encoding="utf-8", errors="ignore")
code = code.replace("\r\n", "\n").replace("\r", "\n")

def ensure_import(src: str, line: str, pat: str = None) -> str:
    import re
    if (pat and re.search(pat, src, flags=re.M)) or (line in src):
        return src
    m = re.search(r"^from\s+flask\s+import\s+.+$", src, flags=re.M)
    pos = m.end() if m else 0
    ins = ("" if pos==0 else "\n") + line + ("\n" if pos==0 else "\n")
    return src[:pos] + ins + src[pos:]

# Ensure imports
code = ensure_import(code, "from flask import render_template, request, redirect, url_for, flash, session, jsonify",
                     pat=r"\bfrom\s+flask\s+import\s+.*\brender_template\b.*\brequest\b.*\bredirect\b.*\burl_for\b.*\bflash\b.*\bsession\b.*\bjsonify\b")
code = ensure_import(code, "import sqlite3", pat=r"\bimport\s+sqlite3\b")
code = ensure_import(code, "import os", pat=r"\bimport\s+os\b")

# DB helpers to ensure tables & wallet mutation
stake_helpers = r"""
# === STAKE: helpers & migrations ===
def __db():
    BASE = os.path.dirname(os.path.abspath(__file__))
    con = sqlite3.connect(os.path.join(BASE, 'survey.db'), timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def __stake_migrate():
    con = __db(); c = con.cursor()
    # users table (ensure)
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, wallet_points INTEGER DEFAULT 0, created_at TEXT)')
    # matches
    c.execute('CREATE TABLE IF NOT EXISTS matches (id INTEGER PRIMARY KEY AUTOINCREMENT, game_id INTEGER NOT NULL, room TEXT NOT NULL, stake INTEGER NOT NULL, status TEXT NOT NULL DEFAULT "open", winner_username TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)')
    # match players
    c.execute('CREATE TABLE IF NOT EXISTS match_players (id INTEGER PRIMARY KEY AUTOINCREMENT, match_id INTEGER NOT NULL, username TEXT NOT NULL, joined_at TEXT DEFAULT CURRENT_TIMESTAMP)')
    # index
    try: c.execute('CREATE INDEX IF NOT EXISTS idx_matches_room ON matches(room)')
    except Exception: pass
    con.commit(); con.close()

def __wallet_get(username):
    con = __db(); c = con.cursor()
    row = c.execute('SELECT wallet_points FROM users WHERE username=?', (username,)).fetchone()
    con.close()
    if not row: return 0
    try: return row['wallet_points']
    except Exception: return row[0]

def __wallet_add(username, delta):
    con = __db(); c = con.cursor()
    c.execute('INSERT OR IGNORE INTO users(username, wallet_points, created_at) VALUES (?, 0, datetime("now"))', (username,))
    c.execute('UPDATE users SET wallet_points = COALESCE(wallet_points,0) + ? WHERE username=?', (delta, username))
    con.commit(); con.close()

def __wallet_sub(username, delta):
    # prevent negative
    cur = __wallet_get(username)
    if cur < delta:
        return False, cur
    __wallet_add(username, -delta)
    return True, cur-delta

def __match_pot(match_id):
    con = __db(); c = con.cursor()
    m = c.execute('SELECT stake FROM matches WHERE id=?', (match_id,)).fetchone()
    if not m: 
        con.close(); 
        return 0
    stake = m['stake'] if hasattr(m, 'keys') else m[0]
    count = c.execute('SELECT COUNT(1) FROM match_players WHERE match_id=?', (match_id,)).fetchone()
    con.close()
    n = count[0] if isinstance(count, tuple) else (count['COUNT(1)'] if hasattr(count, 'keys') else 0)
    return stake * n
# === /STAKE helpers ===
"""

if "__stake_migrate()" not in code:
    m = re.search(r"^\s*if\s+__name__\s*==\s*['\\\"]__main__['\\\"]\s*:\s*$", code, flags=re.M)
    pos = m.start() if m else len(code)
    code = code[:pos] + stake_helpers + code[pos:]

# API routes
stake_routes = r"""
# === STAKE: API routes ===
@app.route('/api/matches', methods=['POST'])
def api_match_create():
    __stake_migrate()
    user = session.get('username')
    if not user: 
        return jsonify(ok=False, error='not authenticated (set username in /portal)'), 401
    data = request.get_json(silent=True) or {}
    try:
        game_id = int(data.get('game_id') or 0)
        stake = int(data.get('stake') or 0)
        room = (data.get('room') or '').strip() or 'public'
    except Exception:
        return jsonify(ok=False, error='invalid payload'), 400
    if game_id <= 0 or stake <= 0: 
        return jsonify(ok=False, error='game_id>0 & stake>0 required'), 400
    ok, _ = __wallet_sub(user, stake)
    if not ok:
        return jsonify(ok=False, error='insufficient points'), 400
    con = __db(); c = con.cursor()
    c.execute('INSERT INTO matches(game_id, room, stake, status) VALUES (?,?,?, "open")',
              (game_id, room, stake))
    mid = c.lastrowid
    c.execute('INSERT INTO match_players(match_id, username) VALUES (?,?)', (mid, user))
    con.commit(); con.close()
    return jsonify(ok=True, match_id=mid)

@app.route('/api/matches/join', methods=['POST'])
def api_match_join():
    __stake_migrate()
    user = session.get('username')
    if not user: 
        return jsonify(ok=False, error='not authenticated'), 401
    data = request.get_json(silent=True) or {}
    mid = int(data.get('match_id') or 0)
    if mid <= 0: return jsonify(ok=False, error='match_id required'), 400
    con = __db(); c = con.cursor()
    m = c.execute('SELECT id, stake, status FROM matches WHERE id=?', (mid,)).fetchone()
    if not m: 
        con.close(); 
        return jsonify(ok=False, error='match not found'), 404
    status = m['status'] if hasattr(m,'keys') else m[2]
    if status != 'open':
        con.close(); 
        return jsonify(ok=False, error='match is not open'), 400
    # already joined?
    found = c.execute('SELECT 1 FROM match_players WHERE match_id=? AND username=?', (mid, user)).fetchone()
    if found:
        con.close(); 
        return jsonify(ok=True, joined=True)
    stake = m['stake'] if hasattr(m,'keys') else m[1]
    ok, _ = __wallet_sub(user, stake)
    if not ok:
        con.close()
        return jsonify(ok=False, error='insufficient points'), 400
    c.execute('INSERT INTO match_players(match_id, username) VALUES (?,?)', (mid, user))
    con.commit(); con.close()
    return jsonify(ok=True, joined=True)

@app.route('/api/matches/report', methods=['POST'])
def api_match_report():
    __stake_migrate()
    user = session.get('username')
    if not user: 
        return jsonify(ok=False, error='not authenticated'), 401
    data = request.get_json(silent=True) or {}
    mid = int(data.get('match_id') or 0)
    winner = (data.get('winner') or '').strip() or user
    if mid <= 0: return jsonify(ok=False, error='match_id required'), 400
    con = __db(); c = con.cursor()
    m = c.execute('SELECT id, status FROM matches WHERE id=?', (mid,)).fetchone()
    if not m: 
        con.close(); 
        return jsonify(ok=False, error='match not found'), 404
    status = m['status'] if hasattr(m,'keys') else m[1]
    if status != 'open':
        con.close(); 
        return jsonify(ok=False, error='already finished'), 400
    # ensure reporter is a participant
    p = c.execute('SELECT 1 FROM match_players WHERE match_id=? AND username=?', (mid, user)).fetchone()
    if not p:
        con.close(); 
        return jsonify(ok=False, error='not a participant'), 403
    # determine pot & pay
    pot = __match_pot(mid)
    c.execute('UPDATE matches SET status="finished", winner_username=? WHERE id=?', (winner, mid))
    con.commit(); con.close()
    if pot > 0:
        __wallet_add(winner, pot)
    return jsonify(ok=True, winner=winner, pot=pot)

@app.route('/api/matches/<int:match_id>', methods=['GET'])
def api_match_get(match_id):
    __stake_migrate()
    con = __db(); c = con.cursor()
    m = c.execute('SELECT id, game_id, room, stake, status, winner_username, created_at FROM matches WHERE id=?', (match_id,)).fetchone()
    if not m: 
        con.close(); 
        return jsonify(ok=False, error='not found'), 404
    players = [r['username'] for r in c.execute('SELECT username FROM match_players WHERE match_id=?', (match_id,)).fetchall()]
    con.close()
    out = dict(m) if hasattr(m,'keys') else {
        'id':m[0],'game_id':m[1],'room':m[2],'stake':m[3],'status':m[4],'winner_username':m[5],'created_at':m[6]
    }
    out['players'] = players
    out['pot'] = __match_pot(match_id)
    return jsonify(ok=True, match=out)

@app.route('/api/leaderboard', methods=['GET'])
def api_leaderboard():
    __stake_migrate()
    game_id = int(request.args.get('game_id') or 0)
    room = (request.args.get('room') or 'public').strip()
    con = __db(); c = con.cursor()
    # wins per user in this game/room
    rows = c.execute('''
        SELECT winner_username as username, COUNT(1) as wins 
        FROM matches 
        WHERE status='finished' AND room=? {game_filter}
        GROUP BY winner_username 
        ORDER BY wins DESC LIMIT 20
    '''.replace("{game_filter}", "AND game_id=?" if game_id>0 else ""), (room,) if game_id<=0 else (room, game_id)).fetchall()
    wins = [(r['username'], r['wins']) for r in rows if r['username']]
    # wallet top (current points) - optional view
    wallet = c.execute('SELECT username, wallet_points FROM users ORDER BY wallet_points DESC LIMIT 20').fetchall()
    con.close()
    return jsonify(ok=True, wins=wins, wallet=[(r['username'], r['wallet_points']) for r in wallet])
# === /STAKE routes ===
"""
# Inject before main
m = re.search(r"^\s*if\s+__name__\s*==\s*['\\\"]__main__['\\\"]\s*:\s*$", code, flags=re.M)
pos = m.start() if m else len(code)
if "/api/matches" not in code:
    code = code[:pos] + stake_routes + code[pos:]

# Ensure migrate called on boot (inside main block)
m2 = re.search(r"^\s*if\s+__name__\s*==\s*['\\\"]__main__['\\\"]\s*:\s*$", code, flags=re.M)
if m2:
    start = m2.end()
    indent = "    "
    block_end = re.search(r"^\S", code[start:], flags=re.M)
    endpos = start + block_end.start() if block_end else len(code)
    block = code[start:endpos]
    if "__stake_migrate()" not in block:
        block = indent + "__stake_migrate()\n" + block
    code = code[:start] + block + code[endpos:]
else:
    code += "\nif __name__ == '__main__':\n    __stake_migrate()\n    app.run(debug=True)\n"

# Write back
APP.write_text(code, encoding="utf-8")

# Update portal.js with match helpers (append if exists)
static_js = ROOT / "static" / "portal.js"
static_js.parent.mkdir(parents=True, exist_ok=True)
extra_js = r"""
// === STAKE helpers ===
async function createMatch(gameId){
  const stake = parseInt(prompt('Stake (points):', '10')||'0',10);
  const room = (window.__ROOM__||'public');
  if(!stake || stake<=0){ alert('Stake > 0 required'); return; }
  try{
    const r = await fetch('/api/matches', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({game_id: gameId, room, stake})});
    const j = await r.json();
    if(!j.ok){ alert(j.error||'failed'); return; }
    alert('Match created! ID: '+j.match_id);
  }catch(e){ alert('Network error'); }
}

async function joinMatch(matchId){
  try{
    const r = await fetch('/api/matches/join', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({match_id: matchId})});
    const j = await r.json();
    if(!j.ok){ alert(j.error||'failed'); return; }
    alert('Joined match.');
  }catch(e){ alert('Network error'); }
}

async function reportWin(matchId, winner){
  try{
    const r = await fetch('/api/matches/report', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({match_id: matchId, winner})});
    const j = await r.json();
    if(!j.ok){ alert(j.error||'failed'); return; }
    alert('Winner: '+j.winner+' | Pot: '+j.pot);
  }catch(e){ alert('Network error'); }
}

async function refreshLeaderboard(gameId, room){
  try{
    const r = await fetch('/api/leaderboard?game_id='+(gameId||0)+'&room='+(encodeURIComponent(room||window.__ROOM__||'public')));
    const j = await r.json();
    if(!j.ok){ return; }
    const list = document.getElementById('lb-wins');
    if(list){
      list.innerHTML = '';
      j.wins.forEach(([u,w])=>{
        const li = document.createElement('li'); li.textContent = u+' — '+w+' wins'; list.appendChild(li);
      });
    }
  }catch(_){}
}
// === /STAKE helpers ===
"""
if static_js.exists():
    static_js.write_text(static_js.read_text(encoding="utf-8") + "\n" + extra_js, encoding="utf-8")
else:
    static_js.write_text(extra_js, encoding="utf-8")

# Update portal/play.html to add minimal stake UI and leaderboard
tpl_play = ROOT / "templates" / "portal" / "play.html"
tpl_play.parent.mkdir(parents=True, exist_ok=True)
play_html = r"""{% extends 'base.html' %}
{% block title %}{{ game.title }}{% endblock %}
{% block content %}
<div class='row'>
  <h2>{{ game.title }}</h2>
  <div class='right' style="display:flex;gap:.5rem;align-items:center;flex-wrap:wrap">
    <span class="pill">ژوور: <b id="room-code">{{ room }}</b></span>
    <a id="room-link" class="btn small secondary" href="{{ url_for('portal_game', game_id=game.id, room=room) }}" target="_blank">بەستەری هاوبەشی</a>
    <button class='btn small' type='button' onclick='copyRoomCode()'>کۆپی کۆد</button>
    <button class='btn small' type='button' onclick='copyRoomLink()'>کۆپی بەستەر</button>
    <button class='btn small' onclick='toggleFull()'>FullScreen</button>
    <a class='btn small' href='{{ url_for('portal_index') }}'>⟵ گەڕانەوە</a>
  </div>
</div>

<div class='card' style='padding:0; overflow:hidden; margin-top:.5rem'>
  <iframe id='gameframe' src='{{ game.embed_url }}' style='width:100%; height:70vh; border:0;'></iframe>
</div>

<div class='card' style="margin-top:1rem">
  <h3>Match / Stake</h3>
  <div class='row' style="gap:.5rem;flex-wrap:wrap">
    <button class='btn' type='button' onclick='createMatch({{ game.id }})'>+ دروستکردنی مچ (Stake)</button>
    <input id="match-id" placeholder="Match ID" style="width:140px">
    <button class='btn secondary' type='button' onclick='joinMatch(parseInt(document.getElementById("match-id").value||"0",10))'>Join</button>
    <input id="winner" placeholder="Winner username" style="width:180px">
    <button class='btn danger' type='button' onclick='reportWin(parseInt(document.getElementById("match-id").value||"0",10), document.getElementById("winner").value||"")'>Report Win</button>
  </div>
</div>

<div class='card' style="margin-top:1rem">
  <h3>Leaderboard ({{ room }})</h3>
  <ul id="lb-wins" style="margin:.4rem 0"></ul>
  <button class='btn small' type='button' onclick='refreshLeaderboard({{ game.id }}, "{{ room }}")'>↻ نوێکردنەوە</button>
</div>

<script src='/static/portal.js'></script>
<script>window.__ROOM__='{{ room|e }}'; refreshLeaderboard({{ game.id }}, '{{ room }}');</script>
{% endblock %}
"""
tpl_play.write_text(play_html, encoding="utf-8")

print("[OK] Stake patch applied. Backup:", str(BAK))
