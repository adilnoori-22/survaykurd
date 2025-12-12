# -*- coding: utf-8 -*-
"""
quick_fix_admin_games_catch_all.py
Fixes AssertionError: overwriting endpoint function: admin_games_catch_all

Usage:
    python quick_fix_admin_games_catch_all.py
    python app.py
"""

import re, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app.py"
if not APP.exists():
    raise SystemExit("ERROR: app.py not found here. Put this file next to app.py and run again.")

# backup
BAK = ROOT / "app.py.bak3"
shutil.copyfile(APP, BAK)

code = APP.read_text(encoding="utf-8", errors="ignore")
code = code.replace("\r\n", "\n").replace("\r", "\n")

# 1) Remove any decorator lines that bind admin_games_catch_all
code = re.sub(
    r"(^\s*)@app\.route\(\s*['\"]/admin/games/<int:game_id>/<path:subpath>['\"][^\)]*\)\s*\n",
    r"\1# [REMOVED duplicate decorator /admin/games/<int:game_id>/<path:subpath>]\n",
    code, flags=re.M
)

# 2) Remove any add_url_rule that targets endpoint=admin_games_catch_all
code = re.sub(
    r"(^\s*)app\.add_url_rule\([^\)]*endpoint\s*=\s*['\"][ ]*admin_games_catch_all[ ]*['\"][^\)]*\)\s*\n",
    r"\1# [REMOVED add_url_rule endpoint='admin_games_catch_all']\n",
    code, flags=re.M
)

# 3) Rename any existing function to avoid collision
code = re.sub(r"\bdef\s+admin_games_catch_all\s*\(", "def admin_games_catch_all_legacy(", code)

# 4) Inject a single guarded binding before main
bind = """
# === SAFE BIND: admin_games_catch_all (guarded) ===
def __agcatch_safe_register():
    if 'admin_games_catch_all' not in app.view_functions:
        def _admin_games_catch_all(game_id, subpath):
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
        app.add_url_rule('/admin/games/<int:game_id>/<path:subpath>',
                         endpoint='admin_games_catch_all',
                         view_func=_admin_games_catch_all,
                         methods=['GET','POST'])
__agcatch_safe_register()
"""
m = re.search(r"^\s*if\s+__name__\s*==\s*['\"]__main__['\"]\s*:\s*$", code, flags=re.M)
pos = m.start() if m else len(code)
code = code[:pos] + bind + code[pos:]

# write back
APP.write_text(code, encoding="utf-8")
print("[OK] Patched admin_games_catch_all safely. Backup at app.py.bak3")
