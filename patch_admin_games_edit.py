#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Usage (Windows CMD, run from project folder that has app.py):
    python patch_admin_games_edit.py

This will modify app.py in-place (and write a backup app.py.bak).
"""

from pathlib import Path
import re
import shutil

APP = Path("app.py")
if not APP.exists():
    raise SystemExit("ERROR: app.py not found in current folder. Run this script inside your project directory.")

src = APP.read_text(encoding="utf-8", errors="ignore")
bak = APP.with_suffix(".py.bak")
shutil.copyfile(APP, bak)

code = src.replace("\r\n", "\n").replace("\r", "\n")

# 1) Remove all route decorators that include admin/games/<int:game_id>/edit
pattern_route = re.compile(r"(^\s*)@app\.route\(\s*['\"]/admin/games/<int:game_id>/edit['\"][^\)]*\)\s*\n", re.M)
code = pattern_route.sub(r"\1# [removed duplicate decorator for /admin/games/<int:game_id>/edit]\n", code)

# 2) Also remove any decorator that explicitly sets endpoint='admin_games_edit'
pattern_endpoint = re.compile(r"(^\s*)@app\.route\([^\)]*endpoint\s*=\s*['\"]admin_games_edit['\"][^\)]*\)\s*\n", re.M)
code = pattern_endpoint.sub(r"\1# [removed duplicate endpoint=admin_games_edit decorator]\n", code)

# 3) Rename any function named admin_games_edit to avoid name collision
code = re.sub(r"\bdef\s+admin_games_edit\s*\(", "def admin_games_edit_legacy(", code)

# 4) Ensure imports for our patch exist
def ensure_import(source: str, import_line: str) -> str:
    if import_line in source:
        return source
    m = re.search(r"^from\s+flask\s+import\s+.+$", source, flags=re.M)
    pos = m.end() if m else 0
    insertion = ("\n" if pos else "") + import_line + ("\n" if pos else "\n")
    return source[:pos] + insertion + source[pos:]

code = ensure_import(code, "from flask import render_template, request, redirect, url_for, flash")
code = ensure_import(code, "import sqlite3")
code = ensure_import(code, "import os")

# 5) Build and inject the single clean binding + aliases
patch_block = """
# === BEGIN: SINGLE BIND for admin_games_edit (auto-patch) ===
def __ag_db():
    try:
        return db()
    except Exception:
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        con = sqlite3.connect(os.path.join(BASE_DIR, 'survey.db'), timeout=30, check_same_thread=False)
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

# Safety: drop any existing mapping for endpoint (runtime)
try:
    app.view_functions.pop('admin_games_edit', None)
except Exception:
    pass

@app.route('/admin/games/<int:game_id>/edit', methods=['GET','POST'], endpoint='admin_games_edit')
@admin_required
def admin_games_edit(game_id):
    if request.method == 'POST':
        __ag_save_game(game_id, request.form)
        try:
            flash('گۆڕانکاریەکان پاشەکەوت کران.', 'success')
        except Exception:
            pass
        return redirect(url_for('admin_games'))
    game = __ag_get_game(game_id)
    try:
        return render_template('admin/games/edit.html', game=game)
    except Exception:
        active = 'checked' if game.get('is_active') else ''
        return (
            \"<!doctype html><meta charset='utf-8'>\"
            f\"<h2>دەستکاری یاری #{game_id}</h2>\"
            \"<form method='post' style='max-width:700px;padding:12px;border:1px solid #ddd;border-radius:10px'>\"
            f\"<label>ناونیشان<br><input name='title' value='{game.get('title','')}' required style='width:100%'></label>\"
            f\"<label>Thumbnail URL<br><input name='thumbnail_url' value='{game.get('thumbnail_url','')}' style='width:100%'></label>\"
            f\"<label>Play URL<br><input name='play_url' value='{game.get('play_url','')}' style='width:100%'></label>\"
            f\"<label>Embed HTML<br><textarea name='embed_html' rows='5' style='width:100%'>{game.get('embed_html','')}</textarea></label>\"
            f\"<label>نمرەی تایبەتی<br><input type='number' name='points_override' value='{game.get('points_override',0)}'></label>\"
            f\"<label>کەمترین چرکە<br><input type='number' name='min_seconds_override' value='{game.get('min_seconds_override',0)}'></label>\"
            f\"<label style='display:flex;align-items:center;gap:.5rem'><input type='checkbox' name='is_active' value='1' {active}> چالاک</label>\"
            \"<div style='margin-top:10px'><button>پاشەکەوت</button> <a href='/admin/games'>گەڕانەوە</a></div>\"
            \"</form>\"
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
        \"<!doctype html><meta charset='utf-8'>\"
        f\"<h3>ڕێگای نەناسراو: <code>{subpath}</code></h3>\"
        f\"<ul><li><a href='/admin/games/{game_id}/edit'>دەستکاری</a></li>\"
        f\"<li><a href='/games/{game_id}/play' target='_blank'>بەزاندن</a></li>\"
        f\"<li><a href='/admin/games'>⟵ گەڕانەوە</a></li></ul>\"
    )
# === END: SINGLE BIND ===
"""

# Inject before main block (or at end)
m = re.search(r"^\s*if\s+__name__\s*==\s*['\\\"]__main__['\\\"]\s*:\s*$", code, flags=re.M)
insert_pos = m.start() if m else len(code)
code = code[:insert_pos] + "\n\n" + patch_block + "\n\n" + code[insert_pos:]

# 6) Guarantee __portal_init_db exists and is called
if not re.search(r"^\s*def\s+__portal_init_db\s*\(", code, flags=re.M):
    code += "\n\ndef __portal_init_db():\n    pass\n"

if not re.search(r"^\s*if\s+__name__\s*==\s*['\\\"]__main__['\\\"]\s*:\s*$", code, flags=re.M):
    code += "\n\nif __name__ == '__main__':\n    __portal_init_db()\n    try:\n        socketio.run(app, host='0.0.0.0', port=5000, debug=True)\n    except NameError:\n        app.run(host='0.0.0.0', port=5000, debug=True)\n"
else:
    m2 = re.search(r"^(?P<indent>\s*)if\s+__name__\s*==\s*['\\\"]__main__['\\\"]\s*:\s*$", code, flags=re.M)
    start = m2.end()
    indent = m2.group('indent') + "    "
    block_end = re.search(r"^\S", code[start:], flags=re.M)
    endpos = start + block_end.start() if block_end else len(code)
    block = code[start:endpos]
    if "__portal_init_db()" not in block:
        block = indent + "__portal_init_db()\n" + block
    code = code[:start] + block + code[endpos:]

APP.write_text(code, encoding="utf-8")
print("Patched app.py (backup at app.py.bak). Success.")
