# -*- coding: utf-8 -*-
r"""
Usage (Windows):
    cd C:\Users\hp\Desktop\survey_app
    python fix_game_points_helper_v3.py
Then:
    python app.py
What it does:
- Removes ANY inline definitions of __points_meta and jinja_game_points_label
- Removes any early lines registering: app.jinja_env.globals['game_points_label'] = jinja_game_points_label
- Inserts (once) after `app = Flask(...)`:
      from points_helper import register_points_helper
      register_points_helper(app)
- Ensures portal_game defines `ad` before render_template(..., ad=ad)
"""
import re, sys
from pathlib import Path

APP = Path("app.py")
if not APP.exists():
    print("ERROR: app.py not found. Run this in the project folder.")
    sys.exit(1)

src = APP.read_text(encoding="utf-8", errors="ignore")

# 1) Nuke any registrations (anywhere)
src, _ = re.subn(
    r"\n\s*app\.jinja_env\.globals\['game_points_label'\]\s*=\s*jinja_game_points_label\s*(#.*)?\n",
    "\n",
    src,
    flags=re.M
)

# 2) Remove helper defs (even malformed). Match from 'def name(' to next top-level def/@/class/if or EOF
def remove_block(name: str, text: str):
    pat = re.compile(
        rf"(?ms)^\s*def\s+{re.escape(name)}\s*\([^\)]*\)\s*:\s*\n(?:[ \t].*\n)*"
    )
    while True:
        text, n = pat.subn("", text, count=1)
        if n == 0: break
    return text

src = remove_block("__points_meta", src)
src = remove_block("jinja_game_points_label", src)

# 3) Also remove any stray lines that contain the Kurdish label string
src, _ = re.subn(r".*پۆینت/خولەک.*\n", "", src)

# 4) Wire external helper after app = Flask(...)
if "register_points_helper(app)" not in src:
    m = re.search(r"app\s*=\s*Flask\([^)]*\)\s*", src)
    if m:
        inject = "\nfrom points_helper import register_points_helper\nregister_points_helper(app)\n"
        src = src[:m.end()] + inject + src[m.end():]

# 5) Ensure portal_game assigns `ad` if ad=ad used
m = re.search(r"@app\.route\(['\"]/portal/game/<int:game_id>['\"][^)]*\)\s+def\s+([A-Za-z_][\w]*)\s*\(", src)
if m:
    func = m.group(1)
    body_pat = re.compile(rf"(def\s+{func}\s*\([^\)]*\):)([\s\S]+?)(?=\n(?:def\s+|@app\.route|class\s+|if\s+__name__|\Z))", re.M)
    fm = body_pat.search(src)
    if fm:
        header, body = fm.group(1), fm.group(2)
        uses_ad_kw = re.search(r"render_template\([^)]*[, ]ad\s*=\s*ad[,\)]", body)
        assigns_ad = re.search(r"\n\s+ad\s*=", body)
        if uses_ad_kw and not assigns_ad:
            try_block = "\n    try:\n        from ads_helper import ad_get_start\n        ad = ad_get_start(int(game_id))\n    except Exception:\n        ad = None\n"
            body = re.sub(r"(\:\s*\n)", r"\1" + try_block, body, count=1)
            src = src[:fm.start(2)] + body + src[fm.end(2):]

APP.write_text(src, encoding="utf-8")
print("[OK] Cleaned app.py. Now run: python app.py")
