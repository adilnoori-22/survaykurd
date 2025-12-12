# -*- coding: utf-8 -*-
"""
apply_patch.py

Run inside your project folder that has app.py:
    python apply_patch.py
Then:
    python app.py

What it does:
- Backup app.py -> app.py.bak
- Remove duplicate bindings for /admin/games/<int:game_id>/edit and endpoint=admin_games_edit
- Rename any existing def admin_games_edit(...) -> def admin_games_edit_legacy(...)
- Inject a safe __portal_init_db() (also migrates users.wallet_points if missing)
- Inject a SINGLE clean binding for admin_games_edit + aliases
- Add /portal routes (+ simple wallet APIs)
- Create templates/portal/*.html and static/portal.js if they do not exist
- Ensure __portal_init_db() is called in main
"""

import os
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app.py"
if not APP.exists():
    raise SystemExit("ERROR: app.py not found in this folder.")

# --- 0) backup
BAK = ROOT / "app.py.bak"
shutil.copyfile(APP, BAK)

code = APP.read_text(encoding="utf-8", errors="ignore")
code = code.replace("\r\n", "\n").replace("\r", "\n")

def ensure_import(src: str, line: str, pat: str = None) -> str:
    if (pat and re.search(pat, src, flags=re.M)) or (line in src):
        return src
    m = re.search(r"^from\s+flask\s+import\s+.+$", src, flags=re.M)
    pos = m.end() if m else 0
    ins = ("" if pos == 0 else "\n") + line + ("\n" if pos == 0 else "\n")
    return src[:pos] + ins + src[pos:]

# 1) Ensure imports
code = ensure_import(
    code,
    "from flask import render_template, request, redirect, url_for, flash, session, jsonify",
    pat=r"\bfrom\s+flask\s+import\s+.*\brender_template\b.*\brequest\b.*\bredirect\b.*\burl_for\b.*\bflash\b.*\bsession\b.*\bjsonify\b",
)
code = ensure_import(code, "import sqlite3", pat=r"\bimport\s+sqlite3\b")
code = ensure_import(code, "import os", pat=r"\bimport\s+os\b")

# 2) Ensure secret key
if not re.search(r"\bapp\.secret_key\s*=", code):
    code += "\napp.secret_key = app.config.get('SECRET_KEY', 'dev-portal-secret')\n"

# 3) Remove duplicate decorators & add_url_rule for admin_games_edit
code = re.sub(
    r"(^\s*)@app\.route\(\s*['\"]/admin/games/<int:game_id>/edit['\"][^\)]*\)\s*\n",
    r"\1# [REMOVED duplicate decorator /admin/games/<int:game_id>/edit]\n",
    code,
    flags=re.M,
)
code = re.sub(
    r"(^\s*)@app\.route\([^\)]*endpoint\s*=\s*['\"][ ]*admin_games_edit[ ]*['\"][^\)]*\)\s*\n",
    r"\1# [REMOVED decorator endpoint='admin_games_edit']\n",
    code,
    flags=re.M,
)
code = re.sub(
    r"(^\s*)app\.add_url_rule\([^\)]*endpoint\s*=\s*['\"][ ]*admin_games_edit[ ]*['\"][^\)]*\)\s*\n",
    r"\1# [REMOVED add_url_rule endpoint='admin_games_edit']\n",
    code,
    flags=re.M,
)

# 4) Rename any existing function to avoid name collision
code = re.sub(r"\bdef\s+admin_games_edit\s*\(", "def admin_games_edit_legacy(", code)

# 5) Inject __portal_init_db (with wallet_points migration) right after imports if missing
if not re.search(r"^\s*def\s+__portal_init_db\s*\(", code, flags=re.M):
    inject_db = (
        "\n# === injected: __portal_init_db (safe) ===\n"
        "def __portal_init_db():\n"
        "    BASE = os.path.dirname(os.path.abspath(__file__))\n"
        "    import sqlite3\n"
        "    con = sqlite3.connect(os.path.join(BASE, 'survey.db'), timeout=30, check_same_thread=False)\n"
        "    con.row_factory = sqlite3.Row\n"
        "    c = con.cursor()\n"
        "    # users\n"
        "    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, wallet_points INTEGER DEFAULT 0, created_at TEXT)')\n"
        "    # add wallet_points if missing\n"
        "    info = c.execute(\"PRAGMA table_info('users')\").fetchall()\n"
        "    colnames = [r['name'] if hasattr(r,'keys') else r[1] for r in info]\n"
        "    if 'wallet_points' not in colnames:\n"
        "        c.execute('ALTER TABLE users ADD COLUMN wallet_points INTEGER DEFAULT 0')\n"
        "        c.execute('UPDATE users SET wallet_points=0 WHERE wallet_points IS NULL')\n"
        "    # games (tolerant)\n"
        "    try:\n"
        "        c.execute('CREATE TABLE IF NOT EXISTS games (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, thumbnail_url TEXT, play_url TEXT, embed_html TEXT, points_override INTEGER DEFAULT 0, min_seconds_override INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1)')\n"
        "    except Exception:\n"
        "        c.execute('CREATE TABLE IF NOT EXISTS games (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, embed_url TEXT, is_active INTEGER DEFAULT 1)')\n"
        "    # settings & ads\n"
        "    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')\n"
        "    c.execute('CREATE TABLE IF NOT EXISTS ads (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, image_url TEXT, click_url TEXT, is_active INTEGER DEFAULT 1)')\n"
        "    # seeds (non-destructive)\n"
        "    if not c.execute(\"SELECT 1 FROM settings WHERE key='points_per_minute'\").fetchone():\n"
        "        c.execute(\"INSERT INTO settings(key,value) VALUES('points_per_minute','10')\")\n"
        "    if not c.execute(\"SELECT 1 FROM settings WHERE key='min_seconds_to_reward'\").fetchone():\n"
        "        c.execute(\"INSERT INTO settings(key,value) VALUES('min_seconds_to_reward','30')\")\n"
        "    con.commit(); con.close()\n"
        "# === /injected ===\n"
    )
    m = re.search(r"(^from\s+flask\s+import.+$)", code, flags=re.M)
    pos = m.end() if m else 0
    code = code[:pos] + ("\n" if pos else "") + inject_db + code[pos:]

# 6) Inject SINGLE CLEAN BIND for admin_games_edit (before main)
single_bind = r"""
# === BEGIN: SINGLE CLEAN BIND of admin_games_edit ===
def __ag_db():
    import sqlite3, os
    BASE = os.path.dirname(os.path.abspath(__file__))
    con = sqlite3.connect(os.path.join(BASE, 'survey.db'), timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con

def __ag_get_game(game_id):
    con = __ag_db(); c = con.cursor()
    try:
        row = c.execute('SELECT id,title,thumbnail_url,play_url,embed_html,points_override,min_seconds_override,is_active FROM games WHERE id=?', (game_id,)).fetchone()
    except Exception:
        row = c.execute('SELECT id,title,embed_url as play_url,is_active FROM games WHERE id=?', (game_id,)).fetchone()
    con.close()
    if not row:
        return {'id': game_id, 'title': '', 'thumbnail_url': '', 'play_url': '', 'embed_html': '', 'points_override': 0, 'min_seconds_override': 0, 'is_active': 1}
    try:
        return dict(row)
    except Exception:
        cols = ['id','title','thumbnail_url','play_url','embed_html','points_override','min_seconds_override','is_active']
        return {k: (row[i] if i < len(row) else None) for i,k in enumerate(cols)}

def __ag_save_game(game_id, form):
    def to_int(v, d=0):
        try: return int(v)
        except Exception: return d
    title = (form.get('title') or '').strip()
    thumbnail_url = (form.get('thumbnail_url') or '').strip()
    play_url = (form.get('play_url') or '').strip()
    embed_html = (form.get('embed_html') or '').strip()
    points_override = to_int(form.get('points_override') or 0)
    min_seconds_override = to_int(form.get('min_seconds_override') or 0)
    is_active = 1 if (form.get('is_active') in ('1','on','true','True')) else 0
    con = __ag_db(); c = con.cursor()
    exists = c.execute('SELECT 1 FROM games WHERE id=?', (game_id,)).fetchone()
    if exists:
        try:
            c.execute('UPDATE games SET title=?, thumbnail_url=?, play_url=?, embed_html=?, points_override=?, min_seconds_override=?, is_active=? WHERE id=?',
                      (title, thumbnail_url, play_url, embed_html, points_override, min_seconds_override, is_active, game_id))
        except Exception:
            c.execute('UPDATE games SET title=?, embed_url=?, is_active=? WHERE id=?',
                      (title, play_url, is_active, game_id))
    else:
        try:
            c.execute('INSERT INTO games (id,title,thumbnail_url,play_url,embed_html,points_override,min_seconds_override,is_active) VALUES (?,?,?,?,?,?,?,?)',
                      (game_id, title, thumbnail_url, play_url, embed_html, points_override, min_seconds_override, is_active))
        except Exception:
            c.execute('INSERT INTO games (id,title,embed_url,is_active) VALUES (?,?,?,?)',
                      (game_id, title, play_url, is_active))
    con.commit(); con.close()

@app.route('/admin/games/<int:game_id>/edit', methods=['GET','POST'], endpoint='admin_games_edit')
@admin_required
def admin_games_edit(game_id):
    if request.method == 'POST':
        __ag_save_game(game_id, request.form)
        try: flash('گۆڕانکاریەکان پاشەکەوت کران.', 'success')
        except Exception: pass
        return redirect(url_for('admin_games'))
    game = __ag_get_game(game_id)
    try:
        return render_template('admin/games/edit.html', game=game)
    except Exception:
        active = 'checked' if game.get('is_active') else ''
        return (
            "<!doctype html><meta charset='utf-8'>"
            f"<h2>دەستکاری یاری #{game_id}</h2>"
            "<form method='post' style='max-width:700px;padding:12px;border:1px solid #ddd;border-radius:10px'>"
            f"<label>ناونیشان<br><input name='title' value='{game.get('title','')}' required style='width:100%'></label>"
            f"<label>Thumbnail URL<br><input name='thumbnail_url' value='{game.get('thumbnail_url','')}' style='width:100%'></label>"
            f"<label>Play URL<br><input name='play_url' value='{game.get('play_url','')}' style='width:100%'></label>"
            f"<label>Embed HTML<br><textarea name='embed_html' rows='5' style='width:100%'>{game.get('embed_html','')}</textarea></label>"
            f"<label>نمرەی تایبەتی<br><input type='number' name='points_override' value='{game.get('points_override',0)}'></label>"
            f"<label>کەمترین چرکە<br><input type='number' name='min_seconds_override' value='{game.get('min_seconds_override',0)}'></label>"
            f"<label style='display:flex;align-items:center;gap:.5rem'><input type='checkbox' name='is_active' value='1' {active}> چالاک</label>"
            "<div style='margin-top:10px'><button>پاشەکەوت</button> <a href='/admin/games'>گەڕانەوە</a></div>"
            "</form>"
        )

@app.route('/admin/games/<int:game_id>/config', methods=['GET','POST'])
@admin_required
def admin_games_config(game_id):
    return redirect(url_for('admin_games_edit', game_id=game_id))

@app.route('/admin/games/<int:game_id>/<path:subpath>', methods=['GET','POST'])
@admin_required
def admin_games_catch_all(game_id, subpath):
    sp = (subpath or '').strip('/').lower()
    if sp in {'config','configuration','settings','options','setup','manage','management','edit'}:
        return redirect(url_for('admin_games_edit', game_id=game_id))
    if sp == 'play':
        return redirect(f'/games/{int(game_id)}/play')
    return (
        "<!doctype html><meta charset='utf-8'>"
        f"<h3>ڕێگای نەناسراو: <code>{subpath}</code></h3>"
        f"<ul><li><a href='/admin/games/{game_id}/edit'>دەستکاری</a></li>"
        f"<li><a href='/games/{game_id}/play' target='_blank'>بەزاندن</a></li>"
        f"<li><a href='/admin/games'>⟵ گەڕانەوە</a></li></ul>"
    )
# === END SINGLE BIND ===
"""
# Insert before main
m = re.search(r"^\s*if\s+__name__\s*==\s*['\\\"]__main__['\\\"]\s*:\s*$", code, flags=re.M)
pos = m.start() if m else len(code)
code = code[:pos] + single_bind + code[pos:]

# 7) Add /portal routes if missing
if "endpoint='portal_index'" not in code and "def portal_index(" not in code:
    portal_routes = r"""
# === Portal routes ===
@app.route('/portal', methods=['GET','POST'], endpoint='portal_index')
def portal_index():
    if request.method == 'POST':
        session['username'] = (request.form.get('username') or '').strip() or None
        return redirect(url_for('portal_index'))
    import sqlite3, os
    BASE = os.path.dirname(os.path.abspath(__file__))
    con = sqlite3.connect(os.path.join(BASE, 'survey.db'), timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    c = con.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS games (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, embed_url TEXT, is_active INTEGER DEFAULT 1)')
    rows = c.execute('SELECT id, title, COALESCE(embed_url,"") as embed_url, COALESCE(is_active,1) as is_active FROM games ORDER BY id DESC').fetchall()
    con.close()
    return render_template('portal/index.html', games=[dict(r) for r in rows], wallet=__portal_wallet())

@app.route('/api/wallet', methods=['GET'])
def api_wallet():
    return jsonify(ok=True, wallet=__portal_wallet())

@app.route('/api/earn', methods=['POST'])
def api_earn():
    data = request.get_json(silent=True) or {}
    try:
        seconds = int(data.get('seconds') or 0)
    except Exception:
        seconds = 0
    if seconds <= 0:
        return jsonify(ok=False, error='seconds<=0'), 400
    user = session.get('username')
    if not user:
        return jsonify(ok=False, error='no user in session'), 400
    add = int(10 * (seconds/60.0))  # default
    import sqlite3, os
    BASE = os.path.dirname(os.path.abspath(__file__))
    con = sqlite3.connect(os.path.join(BASE, 'survey.db'), timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    c = con.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, wallet_points INTEGER DEFAULT 0, created_at TEXT)')
    c.execute('UPDATE users SET wallet_points = COALESCE(wallet_points,0) + ? WHERE username=?', (add, user))
    if c.rowcount == 0:
        c.execute('INSERT INTO users(username, wallet_points, created_at) VALUES (?,?,datetime("now"))', (user, add))
    con.commit(); con.close()
    return jsonify(ok=True, wallet=__portal_wallet())

@app.route('/portal/game/<int:game_id>', methods=['GET'], endpoint='portal_game')
def portal_game(game_id):
    room = request.args.get('room','public')
    import sqlite3, os
    BASE = os.path.dirname(os.path.abspath(__file__))
    con = sqlite3.connect(os.path.join(BASE, 'survey.db'), timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    c = con.cursor()
    row = c.execute('SELECT id,title,play_url,embed_html,embed_url FROM games WHERE id=?', (game_id,)).fetchone())
    con.close()
    if not row:
        return redirect(url_for('portal_index'))
    game = dict(row) if hasattr(row, 'keys') else {}
    title = game.get('title') or f'Game #{game_id}'
    src = (game.get('play_url') or game.get('embed_url') or '').strip() or 'about:blank'
    return render_template('portal/play.html', game={'id':game_id,'title':title,'embed_url':src}, room=room)

def __portal_wallet():
    user = session.get('username')
    if not user:
        return 0
    import sqlite3, os
    BASE = os.path.dirname(os.path.abspath(__file__))
    con = sqlite3.connect(os.path.join(BASE, 'survey.db'), timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    c = con.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, wallet_points INTEGER DEFAULT 0, created_at TEXT)')
    con.commit()
    row = c.execute('SELECT wallet_points FROM users WHERE username=?', (user,)).fetchone()
    if not row:
        c.execute('INSERT INTO users(username, wallet_points, created_at) VALUES (?,?,datetime("now"))', (user, 0))
        con.commit(); con.close(); return 0
    con.close()
    try:
        return row['wallet_points']
    except Exception:
        return row[0] if row else 0
# === /Portal routes ===
"""
    code = code[:pos] + portal_routes + code[pos:]

# 8) Ensure __portal_init_db() is called in main
m2 = re.search(r"^\s*if\s+__name__\s*==\s*['\\\"]__main__['\\\"]\s*:\s*$", code, flags=re.M)
if not m2:
    code += (
        "\n\nif __name__ == '__main__':\n"
        "    __portal_init_db()\n"
        "    try:\n"
        "        socketio.run(app, host='0.0.0.0', port=5000, debug=True)\n"
        "    except Exception:\n"
        "        app.run(host='0.0.0.0', port=5000, debug=True)\n"
    )
else:
    start = m2.end()
    indent = "    "
    block_end = re.search(r"^\S", code[start:], flags=re.M)
    endpos = start + block_end.start() if block_end else len(code)
    block = code[start:endpos]
    if "__portal_init_db()" not in block:
        block = indent + "__portal_init_db()\n" + block
    code = code[:start] + block + code[endpos:]

# 9) Write modified app.py
APP.write_text(code, encoding="utf-8")

# 10) Ensure templates/static exist
tpl_index = """{% extends 'base.html' %}
{% block title %}پۆرتاڵی یاری{% endblock %}
{% block content %}
<h2>پۆرتاڵی یاری</h2>
<form method='post' class='card' style='display:flex;gap:10px;align-items:center'>
  <span class='muted'>ناوی بەکارهێنەر:</span>
  <input name='username' placeholder='ناوت بنووسە' value='{{ session.username or "" }}' style='width:220px'>
  <button class='btn small'>هەڵبژاردن</button>
  <div class='right pill'>🪙 پۆینت: <span id='wallet'>{{ wallet }}</span></div>
</form>
<h3 style='margin-top:16px'>لیستی یارییەکان</h3>
<div class='grid'>
  {% for g in games %}
  <div class='card'>
    <div style='font-weight:700'>{{ g.title }}</div>
    <div class='muted' style='font-size:.9rem'>{{ g.embed_url }}</div>
    <form class='row' onsubmit='event.preventDefault(); playGame({{ g.id }})'>
      <input id='room-{{ g.id }}' placeholder='ناوی ژوور' value='public' style='width:200px'>
      <button class='btn'>دەستپێکردن</button>
    </form>
  </div>
  {% else %}<div class='muted'>هیچ یارییەک نییە.</div>{% endfor %}
</div>
<script src='/static/portal.js'></script>
{% endblock %}
"""
tpl_play = """{% extends 'base.html' %}
{% block title %}{{ game.title }}{% endblock %}
{% block content %}
<div class='row'>
  <h2>{{ game.title }}</h2>
  <div class='right'>
    <button class='btn small' onclick='toggleFull()'>FullScreen</button>
    <a class='btn small' href='{{ url_for('portal_index') }}'>⟵ گەڕانەوە</a>
  </div>
</div>
<div class='card' style='padding:0; overflow:hidden'>
  <iframe id='gameframe' src='{{ game.embed_url }}' style='width:100%; height:70vh; border:0;'></iframe>
</div>
<script src='/static/portal.js'></script>
<script>window.__ROOM__='{{ room|e }}';</script>
{% endblock %}
"""
js_portal = """function playGame(id){
  const room = document.querySelector(`#room-${id}`)?.value || 'public';
  window.location.href = `/portal/game/${id}?room=${encodeURIComponent(room)}`;
}
function toggleFull(){
  const f = document.getElementById('gameframe');
  if(!f) return;
  if (f.requestFullscreen) f.requestFullscreen();
  else if (f.webkitRequestFullscreen) f.webkitRequestFullscreen();
  else if (f.msRequestFullscreen) f.msRequestFullscreen();
}
setInterval(()=>{ fetch('/api/wallet').then(r=>r.json()).then(j=>{ if(j.ok){ const el=document.getElementById('wallet'); if(el) el.textContent=j.wallet; } }); }, 10000);
setInterval(()=>{ fetch('/api/earn', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({seconds:30})})
  .then(r=>r.json()).then(j=>{ if(j.ok){ const el=document.getElementById('wallet'); if(el) el.textContent=j.wallet; } }); }, 30000);
"""

tpl_dir = ROOT / "templates" / "portal"
tpl_dir.mkdir(parents=True, exist_ok=True)
(tpl_dir / "index.html").write_text(tpl_index, encoding="utf-8")
(tpl_dir / "play.html").write_text(tpl_play, encoding="utf-8")

static_dir = ROOT / "static"
static_dir.mkdir(parents=True, exist_ok=True)
(static_dir / "portal.js").write_text(js_portal, encoding="utf-8")

print("[OK] Patch applied. Backup at app.py.bak")
