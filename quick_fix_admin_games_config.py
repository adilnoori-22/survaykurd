# -*- coding: utf-8 -*-
"""
quick_fix_admin_games_config.py
Fixes AssertionError: overwriting endpoint function: admin_games_config

Usage:
    python quick_fix_admin_games_config.py
    python app.py
"""

import re, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app.py"
if not APP.exists():
    raise SystemExit("ERROR: app.py not found here. Put this file next to app.py and run again.")

# backup
BAK = ROOT / "app.py.bak2"
shutil.copyfile(APP, BAK)

code = APP.read_text(encoding="utf-8", errors="ignore")
code = code.replace("\r\n", "\n").replace("\r", "\n")

# 1) Remove any decorator lines that bind admin_games_config
code = re.sub(
    r"(^\s*)@app\.route\(\s*['\"]/admin/games/<int:game_id>/config['\"][^\)]*\)\s*\n",
    r"\1# [REMOVED duplicate decorator /admin/games/<int:game_id>/config]\n",
    code, flags=re.M
)

# 2) Remove any add_url_rule that targets endpoint=admin_games_config
code = re.sub(
    r"(^\s*)app\.add_url_rule\([^\)]*endpoint\s*=\s*['\"][ ]*admin_games_config[ ]*['\"][^\)]*\)\s*\n",
    r"\1# [REMOVED add_url_rule endpoint='admin_games_config']\n",
    code, flags=re.M
)

# 3) Rename any existing function to avoid collision
code = re.sub(r"\bdef\s+admin_games_config\s*\(", "def admin_games_config_legacy(", code)

# 4) Inject a single guarded binding before main
bind = """
# === SAFE BIND: admin_games_config (guarded) ===
def __agc_safe_register():
    if 'admin_games_config' not in app.view_functions:
        def _admin_games_config(game_id):
            return redirect(url_for('admin_games_edit', game_id=game_id))
        app.add_url_rule('/admin/games/<int:game_id>/config',
                         endpoint='admin_games_config',
                         view_func=_admin_games_config,
                         methods=['GET','POST'])
__agc_safe_register()
"""
import re as _re
m = _re.search(r"^\s*if\s+__name__\s*==\s*['\"]__main__['\"]\s*:\s*$", code, flags=_re.M)
pos = m.start() if m else len(code)
code = code[:pos] + bind + code[pos:]

# write back
APP.write_text(code, encoding="utf-8")
print("[OK] Patched admin_games_config safely. Backup at app.py.bak2")
