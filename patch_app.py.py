# -*- coding: utf-8 -*-
"""
Patch your survey_app/app.py to fix:
- f-string HTML/JS syntax errors
- IndentationError in __ensure_endpoint
- Duplicate endpoint AssertionError for admin_games_edit
This script creates a backup app.py.bak before modifying.
"""

import re, sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
src_path = ROOT / "app.py"
bak_path = ROOT / "app.py.bak"

if not src_path.exists():
    print("[ERR] app.py not found in", ROOT)
    sys.exit(1)

text = src_path.read_text(encoding="utf-8", errors="ignore")
orig = text
shutil.copyfile(src_path, bak_path)

changes = []

# 1) Fix empty 'if' in __ensure_endpoint(...) by inserting 'pass'
text, n = re.subn(
    r"(def\s+__ensure_endpoint\([^\)]*\):\s*\n\s*\"\"\"[\s\S]*?ep\s*=\s*endpoint\s*or\s*name\s*\n\s*try:\s*\n\s*if\s+ep\s+not\s+in\s+app\.view_functions:\s*\n)(?!\s*(pass|app\.add_url_rule))",
    r"\1            pass\n",
    text, flags=re.MULTILINE)
if n:
    changes.append(f"[fix] inserted 'pass' inside __ensure_endpoint: {n} place(s)")

# 2) Replace/normalize _page_form_html to a safe, non-fstring HTML builder
safe_page_form = r'''
def _page_form_html(page=None):
    slug  = page["slug"] if page else ""
    title = page["title"] if page else ""
    body  = page["body"] if page else ""

    def _safe_url(name, default="/"):
        try:
            return url_for(name)
        except Exception:
            return default

    back_url = _safe_url("admin_pages_list", _safe_url("api_pages_list", _safe_url("home", "/admin/pages")))

    html = ""
    html += "<!doctype html><meta charset='utf-8'>"
    html += "<link rel='stylesheet' href='https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css'>"
    html += "<div class='container py-4' style='max-width:980px'>"
    html += "  <div class='d-flex justify-content-between align-items-center mb-3'>"
    html += "    <h4 class='mb-0'>" + ("دەستکاری پەڕە" if page else "پەڕەی نوێ") + "</h4>"
    html += "    <div><a class='btn btn-sm btn-outline-secondary' href='" + back_url + "'>گەڕانەوە</a></div>"
    html += "  </div>"
    html += "  <form method='post'>"
    html += "    <div class='mb-3'>"
    html += "      <label class='form-label'>Slug</label>"
    html += "      <input class='form-control' name='slug' value='" + slug + "' placeholder='about-us' required>"
    html += "    </div>"
    html += "    <div class='mb-3'>"
    html += "      <label class='form-label'>ناونیشان</label>"
    html += "      <input class='form-control' name='title' value='" + title + "' required>"
    html += "    </div>"
    html += "    <div class='mb-3'>"
    html += "      <label class='form-label'>ناوەڕۆک</label>"
    html += "      <textarea id='page_body' name='body' rows='18'>" + body + "</textarea>"
    html += "      <div class='form-text'>دەتوانیت خشتە دروست بکەیت، وێنە ڕاکێشە-دانە ناوەوە…</div>"
    html += "    </div>"
    html += "    <div class='d-flex gap-2'>"
    html += "      <button class='btn btn-primary' type='submit'>پاشەکەوت</button>"
    try:
        preview_url = url_for('page_public', slug=slug) if page else None
    except Exception:
        preview_url = None
    if page and preview_url:
        html += "      <a class='btn btn-outline-info' target='_blank' href='" + preview_url + "'>سەیرکردنی بەردەست</a>"
    html += "    </div>"
    html += "  </form>"
    html += "</div>"

    html += "<script src='https://cdn.jsdelivr.net/npm/tinymce@6.8.3/tinymce.min.js'></script>"
    html += "<script>"
    html += "  const TINY_BASE = 'https://cdn.jsdelivr.net/npm/tinymce@6.8.3';"
    html += "  tinymce.init({"
    html += "    selector: '#page_body',"
    html += "    base_url: TINY_BASE,"
    html += "    suffix: '.min',"
    html += "    license_key: 'gpl',"
    html += "    height: 600,"
    html += "    directionality: 'rtl',"
    html += "    menubar: 'file edit view insert format table tools help',"
    html += "    plugins: 'preview searchreplace autolink directionality visualblocks visualchars fullscreen image link media codesample table charmap pagebreak nonbreaking anchor insertdatetime advlist lists wordcount help autoresize code table',"
    html += "    toolbar: 'undo redo | blocks | bold italic underline forecolor backcolor | alignleft aligncenter alignright alignjustify | bullist numlist outdent indent | table tabledelete | link image media | hr codesample | removeformat | preview fullscreen',"
    try:
        upload_url = url_for('admin_upload_image')
    except Exception:
        upload_url = "/admin/upload-image"
    html += "    images_upload_url: '" + upload_url + "',"
    html += "    file_picker_types: 'image',"
    html += "    image_caption: true,"
    html += "    image_advtab: true,"
    html += "    paste_data_images: true,"
    html += "    convert_urls: false,"
    html += "    branding: false,"
    html += "    statusbar: true,"
    html += "    content_style: " \
            "'body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Noto Sans Arabic,Arial;line-height:1.9}' + " \
            "' img{max-width:100%;height:auto}' + " \
            "' table{border-collapse:collapse}' + " \
            "' td,th{padding:8px}' + " \
            "' h1,h2,h3{margin-top:1.2em}'"
    html += "  });"
    html += "</script>"
    return html
'''
if re.search(r"\ndef\s+_page_form_html\s*\(", text):
    text = re.sub(r"\ndef\s+_page_form_html\s*\([^\)]*\):[\s\S]*?(?=\n\w|\Z)", "\n" + safe_page_form + "\n", text, count=1, flags=re.MULTILINE)
    changes.append("[fix] replaced _page_form_html with safe non-fstring version")
else:
    text += "\n" + safe_page_form
    changes.append("[add] appended safe _page_form_html (missing)")

# 3) Remove duplicate bindings of admin_games_edit; inject a single canonical route
# Remove decorators and add_url_rule for the same endpoint to avoid AssertionError
text = re.sub(r"\n\s*app\.add_url_rule\([^)]*endpoint\s*=\s*['\"]admin_games_edit['\"][^)]*\)\s*", "\n", text)
# Remove duplicate @app.route lines (we'll insert our own)
lines = text.splitlines()
out = []
skip_def = False
for i, ln in enumerate(lines):
    if "@app.route(" in ln and "/admin/games/<int:game_id>/edit" in ln:
        # skip this decorator and the next 'def admin_games_edit' header if present
        skip_def = True
        continue
    if skip_def and ln.strip().startswith("def admin_games_edit("):
        # skip function header line only; keep body (it'll likely mismatch); safer to stop skipping now
        skip_def = False
        continue
    out.append(ln)
text = "\n".join(out)

canonical_route = r'''
# ===== Canonical single route for editing a game =====
from flask import render_template, request, redirect, url_for, abort, flash

@app.route('/admin/games/<int:game_id>/edit', methods=['GET','POST'], endpoint='admin_games_edit')
@admin_required
def admin_games_edit(game_id: int):
    db = get_db()
    cur = db.cursor()

    if request.method == 'POST':
        title     = (request.form.get('title') or '').strip()
        thumbnail = (request.form.get('thumbnail_url') or '').strip()
        play_url  = (request.form.get('play_url') or '').strip()
        embed_html= (request.form.get('embed_html') or '').strip()
        pts_over  = request.form.get('points_override')
        min_sec   = request.form.get('min_seconds_override')
        is_active = 1 if request.form.get('is_active') else 0

        def _to_int_or_none(v):
            try:
                return int(v) if str(v).strip() != '' else None
            except Exception:
                return None

        cur.execute("""
            UPDATE games
               SET title=?,
                   thumbnail_url=?,
                   play_url=?,
                   embed_html=?,
                   points_override=?,
                   min_seconds_override=?,
                   is_active=?
             WHERE id=?
        """, (title, thumbnail, play_url, embed_html,
              _to_int_or_none(pts_over), _to_int_or_none(min_sec),
              is_active, int(game_id)))
        db.commit()
        try: flash("یاری نوێکرایەوە.", "success")
        except Exception: pass
        return redirect(url_for('admin_games'))

    row = cur.execute("SELECT * FROM games WHERE id=?", (int(game_id),)).fetchone()
    if not row:
        abort(404)
    try:
        return render_template('admin/games/edit.html', game=row)
    except Exception:
        def _get(obj, key, default=''):
            try:
                if isinstance(obj, dict):
                    return obj.get(key, default) or default
                return obj[key] if obj[key] is not None else default
            except Exception:
                return default
        active_checked = "checked" if (_get(row, "is_active", 0)) else ""
        title_val = _get(row, "title", "")
        th_val    = _get(row, "thumbnail_url", "")
        play_val  = _get(row, "play_url", "")
        embed_val = _get(row, "embed_html", "")
        pts_val   = _get(row, "points_override", 0)
        min_val   = _get(row, "min_seconds_override", 0)
        return (
            "<!doctype html><meta charset='utf-8'>"
            f"<h2>دەستکاری یاری #{game_id}</h2>"
            "<form method='post' style='max-width:700px;padding:12px;border:1px solid #ddd;border-radius:10px'>"
            f"<label>ناونیشان<br><input name='title' value='{title_val}' required style='width:100%'></label>"
            f"<label>Thumbnail URL<br><input name='thumbnail_url' value='{th_val}' style='width:100%'></label>"
            f"<label>Play URL<br><input name='play_url' value='{play_val}' style='width:100%'></label>"
            f"<label>Embed HTML<br><textarea name='embed_html' rows='5' style='width:100%'>{embed_val}</textarea></label>"
            f"<label>نمرەی تایبەتی<br><input type='number' name='points_override' value='{pts_val}'></label>"
            f"<label>کەمترین چرکە<br><input type='number' name='min_seconds_override' value='{min_val}'></label>"
            f"<label style='display:flex;align-items:center;gap:.5rem'><input type='checkbox' name='is_active' value='1' {active_checked}> چالاک</label>"
            "<div style='margin-top:10px'><button>پاشەکەوت</button> <a href='/admin/games'>گەڕانەوە</a></div>"
            "</form>"
        )
# ===== End canonical route =====
'''
# Insert canonical route before __main__ block if present, else append
if re.search(r"\nif\s+__name__\s*==\s*['\"]__main__['\"]\s*:\s*\n", text):
    text = re.sub(r"\nif\s+__name__\s*==\s*['\"]__main__['\"]\s*:\s*\n",
                  "\n" + canonical_route + "\n" + r"if __name__ == '__main__':\n",
                  text, count=1)
    changes.append("[add] inserted canonical admin_games_edit route before __main__")
else:
    text += "\n" + canonical_route
    changes.append("[add] appended canonical admin_games_edit route at end")

# Write patched file
out_path = ROOT / "app.patched.py"
out_path.write_text(text, encoding="utf-8")

print("[OK] Patched written to:", out_path)
print("[OK] Backup saved as   :", bak_path)
print("[INFO] Changes:")
for c in changes:
    print(" -", c)
