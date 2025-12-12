# app.py — Survey Platform (Dynamic Profile Schema + Surveys + Wallet + CMS + Posts API + Pages API)
from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import sqlite3, os, secrets, json, re
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "survey.db")

app = Flask(__name__)

# --- BEGIN RBAC (admin/superadmin) ---
def _ensure_admin_roles_table_and_seed():
    con = get_db(); c = con.cursor()
    try:
        c.execute("""
CREATE TABLE IF NOT EXISTS admin_roles(
    user_id INTEGER PRIMARY KEY,
    role TEXT CHECK(role IN ('admin','superadmin')) NOT NULL
)""")
        try:
            u = c.execute("SELECT id FROM users WHERE email=?", ('adilask3@gmail.com',)).fetchone()
            if u:
                uid = u[0] if isinstance(u, tuple) else (u['id'] if hasattr(u, 'keys') and 'id' in u.keys() else None)
                if uid is not None:
                    r = c.execute("SELECT role FROM admin_roles WHERE user_id=?", (uid,)).fetchone()
                    if not r:
                        c.execute("INSERT OR REPLACE INTO admin_roles(user_id, role) VALUES(?, 'superadmin')", (uid,))
        except Exception:
            pass
        con.commit()
    finally:
        con.close()

def _has_role(role_name: str) -> bool:
    _ensure_admin_roles_table_and_seed()
    try:
        uid = session.get('user_id')
        if not uid: return False
        con = get_db(); c = con.cursor()
        try:
            r = c.execute("SELECT role FROM admin_roles WHERE user_id=?", (uid,)).fetchone()
            if not r: return False
            role = r[0] if isinstance(r, tuple) else (r['role'] if hasattr(r, 'keys') and 'role' in r.keys() else None)
            if role_name == 'admin':
                return role in ('admin','superadmin')
            if role_name == 'superadmin':
                return role == 'superadmin'
            return False
        finally:
            con.close()
    except Exception:
        return False

def _is_superadmin():
    return _has_role('superadmin')
# --- END RBAC (admin/superadmin) ---

from app_ads_config_patch import _install_ads_config
_install_ads_config(app)
from app_games_fullscreen_patch import _install_games_play_fullscreen
_install_games_play_fullscreen(app)
from app_ads_analytics_patch import _install_ads_analytics
_install_ads_analytics(app)
try:
    from app_rooms_patch_safe import _rooms_install_routes_on
    _rooms_install_routes_on(app)
except Exception as e:
    print("rooms patch not installed:", e)
# --- Jinja defaults: callable labels to avoid UndefinedError and str() call issues ---
@app.context_processor
def _inject_template_defaults():
    class _Label(str):
        def __new__(cls, s):
            return super(_Label, cls).__new__(cls, s)
        def __call__(self, *args, **kwargs):
            return str(self)
    return {
        # Games area
        'game_points_label': _Label('Points'),
        'game_min_seconds_label': _Label('Minimum Duration (sec)'),
        'game_active_label': _Label('Active'),
        'game_title_label': _Label('Title'),
        'game_thumbnail_url_label': _Label('Thumbnail URL'),
        'game_play_url_label': _Label('Play URL'),
        'game_embed_html_label': _Label('Embed HTML'),
        # Common UI
        'save_button_label': _Label('Save'),
        'back_button_label': _Label('Back'),
        'status_label': _Label('Status')
    }

app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or "change-me-please"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16MB uploads

from flask import url_for

def _safe_url(ep_name, default="/"):
    try:
        return url_for(ep_name)
    except Exception:
        return default

from flask import url_for

def _safe_url(ep_name, default="/"):
    """هۆکاری گرنگ: هەوڵ دەدات url_for بکات، ئەگەر ئەو endpointە بوونی نەبوو،
    بۆ default دەگەڕێتەوە تا هەڵەی BuildError نەبینیت."""
    try:
        return url_for(ep_name)
    except Exception:
        return default

def _page_form_html(page=None):
    slug  = page["slug"] if page else ""
    title = page["title"] if page else ""
    body  = page["body"] if page else ""

    back_url = _safe_url("admin_pages_list",
                _safe_url("api_pages_list",
                _safe_url("home", "/")))

    return f"""<!doctype html><meta charset="utf-8">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
<div class="container py-4" style="max-width:980px">
  <div class="d-flex justify-content-between align-items-center mb-3">
    <h4 class="mb-0">{'دەستکاری پەڕە' if page else 'پەڕەی نوێ'}</h4>
    <div><a class="btn btn-sm btn-outline-secondary" href="{back_url}">گەڕانەوە</a></div>
  </div>
  <form method="post">
    <div class="mb-3">
      <label class="form-label">Slug</label>
      <input class="form-control" name="slug" value="{slug}" placeholder="about-us" required>
    </div>
    <div class="mb-3">
      <label class="form-label">ناونیشان</label>
      <input class="form-control" name="title" value="{title}" required>
    </div>
    <div class="mb-3">
      <label class="form-label">ناوەڕۆک</label>
      <textarea id="page_body" name="body" rows="18">{body}</textarea>
      <div class="form-text">دەتوانیت خشتە دروست بکەیت، وێنە ڕاکێشە-دانە ناوەوە…</div>
    </div>
    <div class="d-flex gap-2">
      <button class="btn btn-primary" type="submit">پاشەکەوت</button>
      {"<a class='btn btn-outline-info' target='_blank' href='" + url_for('page_public', slug=slug) + "'>سەیرکردنی بەردەست</a>" if page else ""}
    </div>
</div>

<!-- TinyMCE self-hosted (no API key) -->
<script src="https://cdn.jsdelivr.net/npm/tinymce@6.8.3/tinymce.min.js"></script>
<script>
  const TINY_BASE = "https://cdn.jsdelivr.net/npm/tinymce@6.8.3";
  tinymce.init({{
    selector: '#page_body',
    base_url: TINY_BASE,
    suffix: '.min',
    license_key: 'gpl',

    height: 600,
    directionality: 'rtl',
    menubar: 'file edit view insert format table tools help',
    plugins: 'preview searchreplace autolink directionality visualblocks visualchars fullscreen image link media codesample table charmap pagebreak nonbreaking anchor insertdatetime advlist lists wordcount help autoresize code table',
    toolbar: 'undo redo | blocks | bold italic underline forecolor backcolor | alignleft aligncenter alignright alignjustify | bullist numlist outdent indent | table tabledelete | link image media | hr codesample | removeformat | preview fullscreen',

    // 👇 لە پایتۆن هاتووە (هی جینجا نییە)، و چونکە f-stringە، هەموو قوسەکان لەرەوە دووبڵەکراون
    images_upload_url: '{url_for("admin_upload_image")}',

    file_picker_types: 'image',
    image_caption: true,
    image_advtab: true,
    paste_data_images: true,
    convert_urls: false,
    branding: false,
    statusbar: true,

    content_style: 'body{{font-family:system-ui,-apple-system,Segoe UI,Roboto,Noto Sans Arabic,Arial;line-height:1.9}} img{{max-width:100%;height:auto}} table{{border-collapse:collapse}} td,th{{padding:8px}} h1,h2,h3{{margin-top:1.2em}}'
  }});
</script>
"""
# --- Auth decorators (must be defined before routes) ---
from functools import wraps
from flask import session, redirect, url_for, abort, flash

def login_required(f):
    @wraps(f)
    def inner(*args, **kwargs):
        if not session.get("user_id"):
            flash("تکایە بچۆ ژوورەوە.")
            # ئەگەر ڕووتى login هەبوو، بۆ login بڕۆ، نەکەوە ماڵپەڕ
            return redirect(url_for("login") if "login" in app.view_functions else "/")
        return f(*args, **kwargs)
    return inner

def admin_required(f):
    @wraps(f)
    def inner(*args, **kwargs):
        if not session.get("user_id"):
            flash("تکایە بچۆ ژوورەوە.")
            return redirect(url_for("login") if "login" in app.view_functions else "/")
        if not session.get("is_admin"):
            abort(403)
        return f(*args, **kwargs)
    return inner
@app.post("/admin/market/order/<int:order_id>/update")
def admin_market_order_update(order_id):
    if not _is_admin():  # ئەگەر فانکشنی تۆ هەیە
        return ("Not authorized", 403)

    status = (request.form.get("status") or "").strip()
    address = (request.form.get("address") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    tracking_code = (request.form.get("tracking_code") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    member_code = (request.form.get("member_code") or "").strip()

    from datetime import datetime
    now = datetime.utcnow().isoformat()

    con = get_db(); c = con.cursor()
    try:
        # هەوڵ بدە ناونیشان/مۆبایل بە دەست‌ههێنانی خۆکار لە لیستی ئەندامان
        if member_code:
            try:
                mem = c.execute(
                    "SELECT code,name,address,phone FROM market_members WHERE code=?",
                    (member_code,)
                ).fetchone()
                if mem:
                    address = address or (mem["address"] if hasattr(mem, "keys") else mem[2])
                    phone = phone or (mem["phone"] if hasattr(mem, "keys") else mem[3])
            except Exception:
                pass

        # ئەگەر ستونەکان بەنێو خشتەی کۆنت نەدابوو، UPDATE دینامیکەکە هەڵناکەوتەوە
        try:
            c.execute("""
                UPDATE market_orders
                   SET status=?, address=?, phone=?, tracking_code=?, notes=?, member_code=?, updated_at=?
                 WHERE id=?""",
                 (status, address, phone, tracking_code, notes, member_code, now, order_id)
            )
        except Exception:
            # داتابەیسی کۆن: بێ member_code
            c.execute("""
                UPDATE market_orders
                   SET status=?, address=?, phone=?, tracking_code=?, notes=?, updated_at=?
                 WHERE id=?""",
                 (status, address, phone, tracking_code, notes, now, order_id)
            )

        con.commit()
        try: flash("داواکاری نوێکرایەوە.", "success")
        except Exception: pass
    finally:
        con.close()

    return redirect(url_for("admin_market"))

# --- Rich editor: image upload config ---
import os, sqlite3, time
from datetime import datetime
from flask import jsonify, request, url_for
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(__file__)
app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "static", "uploads", "pages")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB
ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}

# ensure upload dir exists
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

def _allowed_image(fname: str) -> bool:
    return "." in fname and fname.rsplit(".", 1)[-1].lower() in ALLOWED_IMAGE_EXT

# هەڵگرتنی قوفڵی DB کەم بکە: (ئەگەر پێشووتر جێگیرت کردووە، هەمان db() بەکارهێنە)
def db():
    con = sqlite3.connect(os.path.join(BASE_DIR, "survey.db"), timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA busy_timeout=30000;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    return con

# --- TinyMCE image upload endpoint ---
# ... کۆدی پێشوو ...

# --- TinyMCE image upload endpoint ---
UPLOAD_PAGES_DIR = os.path.join(BASE_DIR, "static", "uploads", "pages")
os.makedirs(UPLOAD_PAGES_DIR, exist_ok=True)
ALLOWED_IMAGE_EXT = {"png","jpg","jpeg","gif","webp"}
@app.route("/admin/upload-image", methods=["POST"])
@admin_required
def admin_upload_image():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "no file"}), 400
    ext = f.filename.rsplit(".",1)[-1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        return jsonify({"error": "invalid type"}), 400
    base = secure_filename(f.filename.rsplit(".",1)[0])[:50] or "img"
    name = f"{base}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.{ext}"
    f.save(os.path.join(UPLOAD_PAGES_DIR, name))
    return jsonify({"location": url_for("static", filename=f"uploads/pages/{name}")})

    # ناوەکە پاک بکە و timestamp زیاد بکە
    ext = f.filename.rsplit(".", 1)[-1].lower()
    base = secure_filename(f.filename.rsplit(".", 1)[0])[:50] or "img"
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"{base}_{ts}.{ext}"
    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)

    try:
        f.save(save_path)
    except Exception as e:
        return jsonify({"error": f"save failed: {e}"}), 500

    # URL ـی بەکارهێنەر (served by /static)
    url = url_for("static", filename=f"uploads/pages/{filename}", _external=False)
    # TinyMCE expects {location: url}
    return jsonify({"location": url}), 200

# ---------------- Password policy (Server-side) ----------------
# ≥8 chars + at least 1 digit + 1 symbol, and must match confirm
PWD_REGEX = re.compile(r'^(?=.*\d)(?=.*[\W_]).{8,}$')

def validate_password(password: str, confirm: str):
    if password != confirm:
        return False, "پاسۆرد و دووبارە پاسۆرد یەک ناچن."
    if len(password) < 8:
        return False, "پاسۆرد نابێت کەمتر لە ٨ پیت بێت."
    if not PWD_REGEX.search(password):
        return False, "پاسۆرد پێویستە لانیکەم ١ ژمارە و ١ هێما لەخۆ بگرێت."
    return True, ""

# ------------ Uploads ------------
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {"png","jpg","jpeg","gif","webp","svg","pdf","mp4","mov","avi","mp3","wav"}

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
# ⬇️ لەسەرەتا دڵنیابە ئەمانە تۆمار کراون:
from flask import current_app, url_for

# ⬇️ ئەم context_processor ـە هەموو شوێنە گرنگەکان بۆ قالیبەکان دابین دەکات
@app.context_processor
def inject_template_globals():
    def has_endpoint(name: str) -> bool:
        try:
            return name in current_app.view_functions
        except Exception:
            return False

    def safe_url(endpoint: str, **kwargs) -> str:
        # بە جای url_for ڕاستەوخۆ، سەرەتا دڵنیابە ڕووتەکە هەیە
        if has_endpoint(endpoint):
            try:
                return url_for(endpoint, **kwargs)
            except Exception:
                return "#"
        return "#"

    # get_setting لەوانەیە لە پڕۆژەکەت هەبێت؛ ئەگەر نەبێت، ئەم گەرەکیەش بەردەست دەکات
    def _get_setting(key, default=None):
        try:
            return get_setting(key, default)  # ئەگەر پێشتر دیاریکراوە
        except Exception:
            return default

    return {
        "current_app": current_app,  # 🔧 دابینکردنی current_app بۆ قالیبەکان
        "has_endpoint": has_endpoint,
        "safe_url": safe_url,
        "get_setting": _get_setting,
    }
# --- Image upload for TinyMCE (no docstring to avoid indent issues) ---
from flask import request, jsonify, url_for
from werkzeug.utils import secure_filename
from datetime import datetime
import os
from flask import url_for
def _safe_url(ep, default="/"):
    try: return url_for(ep)
    except Exception: return default
ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
# دڵنیابە لە سەرەتا دانراوە:
# app.config["UPLOAD_FOLDER"] = os.path.join(BASE_DIR, "static", "uploads", "pages")
# os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

# ------------ DB helpers ------------
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON;")
    return con
def migrate():
    con = db(); c = con.cursor()
def db():
    con = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    # PRAGMA ـەکان: یارمەتی دەدەن کێشەی قوفڵەکە کەم بێت
    con.execute("PRAGMA journal_mode=WAL;")         # Readers/Writer بە ئاسانی‌تر
    con.execute("PRAGMA busy_timeout=30000;")       # چاوەڕوانی تا 30s کاتێک قوفڵە هەیە
    con.execute("PRAGMA synchronous=NORMAL;")       # بێهێزکردنی I/O کەمێک
    con.execute("PRAGMA foreign_keys=ON;")          # بۆ تەناسوبی جۆینەکان
    return con
    # users
    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE,
      email TEXT UNIQUE,
      password_hash TEXT NOT NULL,
      is_admin INTEGER NOT NULL DEFAULT 0,
      email_verified INTEGER NOT NULL DEFAULT 0,
      email_verify_token TEXT,
      reset_token TEXT,
      reset_token_exp DATETIME,
      api_token TEXT,
      api_token_exp DATETIME,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # core profile
    c.execute("""
    CREATE TABLE IF NOT EXISTS profiles(
      user_id INTEGER PRIMARY KEY,
      full_name TEXT,
      middle_name TEXT,
      nickname TEXT,
      gender TEXT,
      phone_code TEXT,
      phone TEXT,
      age INTEGER,
      degree TEXT,
      city TEXT,
      family_status TEXT,
      work_type TEXT,
      political_member TEXT,
      own_house TEXT,
      own_car TEXT,
      wallet_points INTEGER NOT NULL DEFAULT 0,
      updated_at DATETIME,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # detailed per-section (snapshot + awarding)
    c.execute("""
    CREATE TABLE IF NOT EXISTS profile_details(
      user_id INTEGER NOT NULL,
      section TEXT NOT NULL,
      payload_json TEXT NOT NULL,
      awarded_points INTEGER NOT NULL DEFAULT 0,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(user_id, section),
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    # app settings
    c.execute("""
    CREATE TABLE IF NOT EXISTS app_settings(
      key TEXT PRIMARY KEY,
      value TEXT
    );
    """)

    # CMS pages
    c.execute("""
    CREATE TABLE IF NOT EXISTS pages(
      slug TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      html  TEXT NOT NULL,
      updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # wallet
    c.execute("""
    CREATE TABLE IF NOT EXISTS wallet_transactions(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      type TEXT NOT NULL,   -- earn | spend | adjust | payout
      points INTEGER NOT NULL,
      note TEXT,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS payout_requests(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      method TEXT NOT NULL,     -- bank_card | mobile_topup
      provider TEXT,
      account TEXT NOT NULL,
      points INTEGER NOT NULL,
      money_cents INTEGER NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      processed_at DATETIME,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS ads(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      image_url TEXT,
      link_url TEXT,
      reward_points INTEGER DEFAULT 2,
      is_active INTEGER NOT NULL DEFAULT 1,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # Add reward_points column if it doesn't exist (for existing databases)
    try:
        c.execute("ALTER TABLE ads ADD COLUMN reward_points INTEGER DEFAULT 2")
    except sqlite3.OperationalError:
        # Column already exists
        pass
   
    c.execute("""
    CREATE TABLE IF NOT EXISTS games(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      embed_url TEXT,
      is_active INTEGER NOT NULL DEFAULT 1,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # surveys
    c.execute("""
    CREATE TABLE IF NOT EXISTS surveys(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      description TEXT,
      is_active INTEGER NOT NULL DEFAULT 1,
      reward_points INTEGER NOT NULL DEFAULT 10,
      allow_multiple INTEGER NOT NULL DEFAULT 0,
      created_by INTEGER,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(created_by) REFERENCES users(id) ON DELETE SET NULL
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS survey_questions(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      survey_id INTEGER NOT NULL,
      q_text TEXT NOT NULL,
      q_type TEXT NOT NULL,        -- text/textarea/number/date/select/radio/checkbox/yesno/rating5/scale10
      options_json TEXT,
      required INTEGER NOT NULL DEFAULT 0,
      position INTEGER NOT NULL DEFAULT 0,
      show_if_json TEXT,
      FOREIGN KEY(survey_id) REFERENCES surveys(id) ON DELETE CASCADE
    );
    """)
    # submissions & answers
    c.execute("""CREATE TABLE IF NOT EXISTS survey_submissions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        survey_id INTEGER NOT NULL,
        user_id INTEGER,
        submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS survey_answers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        submission_id INTEGER NOT NULL,
        question_id INTEGER NOT NULL,
        answer_text TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS survey_responses(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      survey_id INTEGER NOT NULL,
      user_id INTEGER,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY(survey_id) REFERENCES surveys(id) ON DELETE CASCADE,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS survey_response_items(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      response_id INTEGER NOT NULL,
      question_id INTEGER NOT NULL,
      answer_text TEXT,
      FOREIGN KEY(response_id) REFERENCES survey_responses(id) ON DELETE CASCADE,
      FOREIGN KEY(question_id) REFERENCES survey_questions(id) ON DELETE CASCADE
    );
    """)

    # dynamic profile schema
    c.execute("""
    CREATE TABLE IF NOT EXISTS profile_packages(
      code TEXT PRIMARY KEY,             -- e.g., about/assets/work/social or any custom
      title TEXT NOT NULL,
      position INTEGER NOT NULL DEFAULT 0
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS profile_questions(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      pkg_code TEXT NOT NULL,
      q_text TEXT NOT NULL,
      q_type TEXT NOT NULL,             -- text/textarea/number/date/select/radio/checkbox/yesno/rating5/scale10
      options_json TEXT,
      required INTEGER NOT NULL DEFAULT 0,
      position INTEGER NOT NULL DEFAULT 0,
      expose_for_rules INTEGER NOT NULL DEFAULT 0,
      FOREIGN KEY(pkg_code) REFERENCES profile_packages(code) ON DELETE CASCADE
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS profile_answers(
      user_id INTEGER NOT NULL,
      pkg_code TEXT NOT NULL,
      question_id INTEGER NOT NULL,
      answer_text TEXT,
      PRIMARY KEY(user_id, question_id),
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY(pkg_code) REFERENCES profile_packages(code) ON DELETE CASCADE,
      FOREIGN KEY(question_id) REFERENCES profile_questions(id) ON DELETE CASCADE
    );
    """)

    # survey eligibility
    c.execute("""
    CREATE TABLE IF NOT EXISTS survey_eligibility(
      survey_id INTEGER PRIMARY KEY,
      rules_json TEXT NOT NULL,
      FOREIGN KEY(survey_id) REFERENCES surveys(id) ON DELETE CASCADE
    );
    """)

    # posts (for public/user posts with optional image)
    c.execute("""
    CREATE TABLE IF NOT EXISTS posts(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      title   TEXT NOT NULL,
      body    TEXT,
      image_url TEXT,
      is_published INTEGER NOT NULL DEFAULT 1,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at DATETIME,
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    c.execute("CREATE INDEX IF NOT EXISTS idx_posts_pub ON posts(is_published, id DESC);")

    # NEW: logs for ad views & game plays (once per day per item)
    c.execute("""
    CREATE TABLE IF NOT EXISTS ad_views(
      user_id INTEGER NOT NULL,
      ad_id   INTEGER NOT NULL,
      day     TEXT    NOT NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(user_id, ad_id, day),
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY(ad_id)   REFERENCES ads(id)   ON DELETE CASCADE
    );
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS game_plays(
      user_id INTEGER NOT NULL,
      game_id INTEGER NOT NULL,
      day     TEXT    NOT NULL,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
      PRIMARY KEY(user_id, game_id, day),
      FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY(game_id) REFERENCES games(id) ON DELETE CASCADE
    );
    """)

    # defaults
    def set_if_missing(k, v):
        row = c.execute("SELECT 1 FROM app_settings WHERE key=?", (k,)).fetchone()
        if not row:
            c.execute("INSERT INTO app_settings(key,value) VALUES (?,?)", (k, str(v)))

    set_if_missing("money_per_point", "10")        # IQD per point
    set_if_missing("min_payout_points", "100")
    set_if_missing("pts_profile_section", "20")

    # NEW default rewards for ads & games
    set_if_missing("pts_ad_view", "2")
    set_if_missing("pts_game_play", "5")

    # seed core packages (once)
    if not c.execute("SELECT 1 FROM profile_packages LIMIT 1").fetchone():
        c.executemany("INSERT INTO profile_packages(code,title,position) VALUES (?,?,?)", [
            ("about","دەربارەی من", 10),
            ("assets","سەرمایە", 20),
            ("work","کار", 30),
            ("social","کۆمەڵایەتی/سیاسی", 40),
        ])

    con.commit(); con.close()
# PATCH: DB safety (زیادکردنی game_ads و ستونەکان)
def _ensure_game_ads_schema():
    con = db(); c = con.cursor()
    # games: ستونە تایبەتیەکان
    c.execute("""CREATE TABLE IF NOT EXISTS games(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      title TEXT NOT NULL,
      play_url TEXT,
      embed_html TEXT,
      thumbnail_url TEXT,
      is_active INTEGER NOT NULL DEFAULT 1,
      points_override INTEGER,
      min_seconds_override INTEGER,
      created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    try: c.execute("ALTER TABLE games ADD COLUMN points_override INTEGER")
    except Exception: pass
    try: c.execute("ALTER TABLE games ADD COLUMN min_seconds_override INTEGER")
    except Exception: pass

    # خشتەی پێوەستکردنی ریکلام بۆ یاری
    c.execute("""CREATE TABLE IF NOT EXISTS game_ads(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      game_id INTEGER NOT NULL,
      ad_id INTEGER NOT NULL,
      position TEXT NOT NULL DEFAULT 'pre'  -- pre | mid | post
    )""")
    con.commit(); con.close()

_ensure_game_ads_schema()

migrate()

# ------------ helpers / context ------------
def dev_send_email(purpose, to_email, link):
    print(f"[DEV-EMAIL] {purpose} -> {to_email}\n  {link}\n")

def get_setting(key, default=None):
    con = db(); c = con.cursor()
    row = c.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    con.close()
    return (row["value"] if row else default)

def _safe_url(ep_name, default="/"):
    # Try url_for; if endpoint doesn't exist, return fallback URL
    try:
        return url_for(ep_name)
    except Exception:
        return default

def public_page_url(slug):
    # Accept dict/object/str and return a public page URL
    if isinstance(slug, dict):
        s = slug.get("slug") or slug.get("path") or slug.get("code")
    else:
        s = getattr(slug, "slug", None) if not isinstance(slug, str) else slug
    if not s:
        return "#"
    try:
        return url_for("page_public", slug=s)
    except Exception:
        return f"/p/{s}"

    # هەوڵ‌دان لە چەند ناوی ڕووتی زۆر بەکاربردراو
    for ep in ("page_public", "page_view", "cms_page"):
        try:
            return url_for(ep, slug=slug)
        except Exception:
            pass

    # هەوڵ: ئەگەر ناوی endpoint هەمان ناوی slug بێت (بۆ پەڕەی تایبەت)
    try:
        return url_for(slug)
    except Exception:
        return "#"

def set_setting(key, value):
    con = db(); c = con.cursor()
    if c.execute("SELECT 1 FROM app_settings WHERE key=?", (key,)).fetchone():
        c.execute("UPDATE app_settings SET value=? WHERE key=?", (str(value), key))
    else:
        c.execute("INSERT INTO app_settings(key,value) VALUES (?,?)", (key, str(value)))
    con.commit(); con.close()
# === DB shim (fix NameError: get_db) ================================
# Paste this block near the TOP of app.py (right after imports).
import os, sqlite3

def _detect_db_path():
    try:
        # Try Flask app config if available
        return (app.config.get("DATABASE")
                or app.config.get("DB_PATH")
                or "survey.db")
    except Exception:
        # Fallback to env or default
        return os.environ.get("SURVEY_DB", "survey.db")

_DB_PATH = _detect_db_path()

# If your project doesn't already define get_db(), provide one.
if "get_db" not in globals():
    def get_db():
        con = sqlite3.connect(_DB_PATH)
        con.row_factory = sqlite3.Row
        return con


# --- Members directory (market_members) ---
def _ensure_market_members_table():
    con = get_db(); c = con.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS market_members(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        user_id INTEGER,
        name TEXT,
        address TEXT,
        phone TEXT
    )""")
    con.commit(); con.close()

def _member_by_code(c, code):
    if not code: return None
    return c.execute("SELECT code,name,address,phone,user_id FROM market_members WHERE code=?", (code,)).fetchone()
# Some parts of the app might call db() instead; alias to get_db() if missing.
if "db" not in globals():
    db = get_db
# =====================================================================

# ـــــــــ Schema migration: ئەگەر ستوون نییە، خۆکارانە زیاد بکە ـــــــــ
import sqlite3

def migrate_schema():
    con = db(); c = con.cursor()

    # یارمەتی: زیادکردنی ستوون بە ئامادەکردن
    def add_col(table, name, spec):
        info = c.execute(f"PRAGMA table_info({table})").fetchall()
        # sqlite3.Row یان tuple ـەکان هەردوو ڕێگری بکە
        names = { (row["name"] if isinstance(row, sqlite3.Row) else row[1]) for row in info }
        if name not in names:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {name} {spec}")

    # دڵنیابە خشتەی games هەیە (ئەگەر نییە، بنەڕەت دروست بکە بە لاوازترین دیفینیشن)
    c.execute("CREATE TABLE IF NOT EXISTS games (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL)")

    # ستوونە پێویستەکان بۆ یاری — هەر یەک نیبوو، زیاد بکرێت
    add_col("games", "play_url", "TEXT")
    add_col("games", "embed_html", "TEXT")
    add_col("games", "thumbnail_url", "TEXT")
    add_col("games", "is_active", "INTEGER DEFAULT 1")
    add_col("games", "points_override", "INTEGER")
    add_col("games", "min_seconds_override", "INTEGER")
    add_col("games", "created_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")
    # removed invalid placeholder column

    con.commit(); con.close()

# بانگکردنی مایگریشن لە کاتی هەڵاوساندنی ئەپ
migrate_schema()

@app.context_processor
def inject_globals():
    return {
        "now": datetime.utcnow(),
        "money_per_point": int(get_setting("money_per_point","10")),
        "min_payout_points": int(get_setting("min_payout_points","100"))
    }
@app.context_processor
def _inject_links_helper():
    from flask import url_for, current_app

    def public_page_url(slug: str) -> str:
        """
        هەرکات ناوی slug هاوشێوەی ناوی endpoint بێت (بۆ نموونە 'wallet'),
        پێشتر بڕۆ بۆ هەمان ڕووتی ڕاستەوخۆ. وەگرە /p/<slug> کاتێک
        ئەو endpointە بوونی نییە.
        """
        if not slug:
            return "#"
        # 1) هەوڵ بده وەک ناوی endpoint ـی فڵاسک بهێنیت
        if slug in current_app.view_functions:
            try:
                return url_for(slug)
            except Exception:
                pass
        # 2) کەبوونی ڕووتی داینامیکی پەڕەکان
        try:
            return url_for("page_by_slug", slug=slug)
        except Exception:
            return f"/p/{slug}"

    return {"public_page_url": public_page_url}


def login_required(f):
    @wraps(f)
    def _w(*a, **k):
        if not session.get("user_id"):
            flash("تکایە سەرەتا چوونەژوورەوە بکە.")
            return redirect(url_for("login"))
        return f(*a, **k)
    return _w

def admin_required(f):
    @wraps(f)
    def _w(*a, **k):
        if not session.get("is_admin"):
            flash("دەستپێگەیشتنی ئەdmین نییە.")
            return redirect(url_for("index"))
        return f(*a, **k)
    return _w

def slugify(s):
    s = (s or "").strip().lower()
    s = re.sub(r"[^a-z0-9\-]+", "-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "page"

def add_points(user_id, pts, note, typ="earn"):
    con = db(); c = con.cursor()
    c.execute("UPDATE profiles SET wallet_points = COALESCE(wallet_points,0) + ? WHERE user_id=?", (pts, user_id))
    c.execute("INSERT INTO wallet_transactions(user_id,type,points,note) VALUES (?,?,?,?)",
              (user_id, typ, pts, note))
    con.commit(); con.close()

# NEW: utility — check all profile packages completed

def completed_all_packages(user_id):
    con = db(); c = con.cursor()
    req = [r["code"] for r in c.execute("SELECT code FROM profile_packages").fetchall()]
    done = {r["section"] for r in c.execute("SELECT section FROM profile_details WHERE user_id=?", (user_id,)).fetchall()}
    con.close()
    missing = [code for code in req if code not in done]
    return len(missing) == 0, missing

# ---------------- API helpers ----------------
def api_json(ok=True, data=None, error=None, status=200):
    payload = {"ok": bool(ok)}
    if error:
        payload["error"] = str(error)
    if data is not None:
        payload["data"] = data
    return jsonify(payload), status

def row_to_post_dict(r):
    return {
        "id": r["id"],
        "user_id": r["user_id"],
        "title": r["title"],
        "body": r["body"],
        "image_url": r["image_url"],
        "is_published": bool(r["is_published"]),
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }

def save_uploaded_file(f):
    if not f or f.filename == "":
        return None
    if not allowed_file(f.filename):
        raise ValueError("فایلی نادرست/پشتگیری نابۆ (extension).")
    name = secure_filename(f.filename)
    base, ext = os.path.splitext(name)
    unique = f"{slugify(base)}-{secrets.token_hex(4)}{ext.lower()}"
    f.save(os.path.join(UPLOAD_FOLDER, unique))
    return url_for("static", filename=f"uploads/{unique}", _external=True)

def _issue_api_token(user_id, hours=24*30):
    tok = secrets.token_urlsafe(32)
    exp = (datetime.utcnow() + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    con = db(); c = con.cursor()
    c.execute("UPDATE users SET api_token=?, api_token_exp=? WHERE id=?", (tok, exp, user_id))
    con.commit(); con.close()
    return tok, exp

def _find_user_by_token(token):
    if not token:
        return None
    con = db(); c = con.cursor()
    u = c.execute("SELECT * FROM users WHERE api_token=?", (token,)).fetchone()
    if not u:
        con.close(); return None
    try:
        exp = datetime.strptime(u["api_token_exp"], "%Y-%m-%d %H:%M:%S") if u["api_token_exp"] else None
    except Exception:
        exp = None
    if (exp is None) or (datetime.utcnow() > exp):
        con.close(); return None
    con.close()
    return u

def api_auth_required(f):
    @wraps(f)
    def _w(*a, **k):
        auth = request.headers.get("Authorization","")
        token = ""
        if auth.lower().startswith("bearer "):
            token = auth.split(None, 1)[1].strip()
        user = _find_user_by_token(token)
        if not user:
            return api_json(False, error="Unauthorized", status=401)
        request.api_user = user
        return f(*a, **k)
    return _w

def api_admin_required(f):
    @wraps(f)
    def _w(*a, **k):
        user = getattr(request, "api_user", None)
        if not user or not bool(user["is_admin"]):
            return api_json(False, error="Admin only", status=403)
        return f(*a, **k)
    return _w

# Minimal CORS (adjust for production)
@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, DELETE, OPTIONS"
    return resp
# ───── Endpoint aliases (compat) ─────
# هەردوو ناوەکان کار بکەن: admin_ads_edit و admin_ad_edit
# ئەگەر یەکێک تۆمار بوو و ئەوی تر نەبوو، ئەلیاس دەمانی‌نووسێت.

# ------------ Auth ------------
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        # Fields mapped to register.html
        first_name  = (request.form.get("first_name","") or "").strip()
        father_name = (request.form.get("father_name","") or "").strip()
        nickname    = (request.form.get("nickname","") or "").strip()
        gender      = (request.form.get("gender","") or "").strip()
        phone_code  = (request.form.get("phone_code","") or "").strip() or "+964"
        phone_raw   = request.form.get("phone","") or ""
        phone       = re.sub(r"[^\d]", "", phone_raw)
        email       = (request.form.get("email","") or "").strip().lower()
        username_in = (request.form.get("username","") or "").strip()
        password    = request.form.get("password","") or ""
        confirm     = request.form.get("confirm_password","") or ""

        if not first_name or not father_name or not gender or not phone or not email or not password or not confirm:
            flash("تکایە هەموو خانەکان پڕبکەوە.", "error")
            return render_template("register.html")

        ok, msg = validate_password(password, confirm)
        if not ok:
            flash(msg, "error")
            return render_template("register.html")

        if username_in:
            username = slugify(username_in)[:30]
        else:
            base = email.split("@")[0] if "@" in email else first_name
            username = slugify(base)[:30] or f"user{secrets.randbelow(9999)}"

        con = db(); c = con.cursor()
        try:
            c.execute("INSERT INTO users(username,email,password_hash,is_admin,email_verified) VALUES (?,?,?,0,0)",
                      (username, email, generate_password_hash(password)))
            uid = c.lastrowid
            c.execute("""
              INSERT INTO profiles(user_id,full_name,middle_name,nickname,gender,phone_code,phone,wallet_points,updated_at)
              VALUES (?,?,?,?,?,?,?,0,CURRENT_TIMESTAMP)
            """, (uid, first_name, father_name, nickname, gender, phone_code, phone))
            token = secrets.token_urlsafe(32)
            c.execute("UPDATE users SET email_verify_token=? WHERE id= ?", (token, uid))
            con.commit()
        except sqlite3.IntegrityError:
            con.rollback(); con.close()
            flash("ئەم ئیمەیلە یان ناوی بەکارهێنەر پێشتر هەیە.", "error")
            return render_template("register.html")
        con.close()

        verify_link = url_for("verify_email", token=token, _external=True)
        dev_send_email("Verify Email", email, verify_link)
        return render_template("auth_verify_sent.html", email=email, link=verify_link)

    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        user_or_email = request.form.get("user_or_email","").strip().lower()
        password = request.form.get("password","")
        con = db(); c = con.cursor()
        u = c.execute("SELECT * FROM users WHERE username=? OR email=?", (user_or_email, user_or_email)).fetchone()
        con.close()
        if u and check_password_hash(u["password_hash"], password):
            if not (u["email_verified"] or 0):
                return render_template("auth_verify_notice.html", email=u["email"])
            session["user_id"] = u["id"]
            session["username"] = u["username"] or (u["email"] or "")
            session["is_admin"] = bool(u["is_admin"])
            flash("بەخێربێیت!")
            return redirect(url_for("index"))
        flash("زانیاری چوونەژوورەوە هەڵەیە.", "error")
    return render_template("auth_login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("دەرچوویت.")
    return redirect(url_for("index"))

@app.route("/verify-email")
def verify_email():
    token = request.args.get("token","").strip()
    if not token: abort(400)
    con = db(); c = con.cursor()
    u = c.execute("SELECT id FROM users WHERE email_verify_token=?", (token,)).fetchone()
    if not u:
        con.close(); flash("Token نادروستە یان بەسەرچووە."); return redirect(url_for("login"))
    c.execute("UPDATE users SET email_verified=1, email_verify_token=NULL WHERE id=?", (u["id"],))
    con.commit(); con.close()
    flash("ئیمەیڵ سەلمێندرایە. تکایە دوبارە بچۆ ناو هەژمارەکەت.")
    return redirect(url_for("login"))

@app.route("/verify/resend", methods=["GET","POST"])
def verify_resend():
    if request.method == "POST":
        email = (request.form.get("email","") or "").strip().lower()
        con = db(); c = con.cursor()
        u = c.execute("SELECT id,email_verified FROM users WHERE email=?", (email,)).fetchone()
        if not u:
            con.close(); flash("ئه‌و ئیمەیڵە نەدۆزرایەوە."); return redirect(url_for("verify_resend"))
        if u["email_verified"]:
            con.close(); flash("ئه‌م ئیمەیڵە پێشتر سەلمێندرایە."); return redirect(url_for("login"))
        token = secrets.token_urlsafe(32)
        c.execute("UPDATE users SET email_verify_token=? WHERE id=?", (token, u["id"]))
        con.commit(); con.close()
        link = url_for("verify_email", token=token, _external=True)
        dev_send_email("Verify Email (Resend)", email, link)
        return render_template("auth_verify_sent.html", email=email, link=link)
    email = request.args.get("email","")
    return render_template("auth_verify_resend.html", email=email)

@app.route("/password/forgot", methods=["GET","POST"])
def password_forgot():
    if request.method == "POST":
        email = (request.form.get("email","") or "").strip().lower()
        con = db(); c = con.cursor()
        u = c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if u:
            token = secrets.token_urlsafe(32)
            exp = (datetime.utcnow() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
            c.execute("UPDATE users SET reset_token=?, reset_token_exp=? WHERE id=?", (token, exp, u["id"]))
            con.commit()
            link = url_for("password_reset", token=token, _external=True)
            dev_send_email("Password Reset", email, link)
            con.close()
            return render_template("auth_reset_sent.html", email=email, link=link)
        con.close()
        return render_template("auth_reset_sent.html", email=email, link=None)
    return render_template("auth_forgot.html")

@app.route("/password/reset/<token>", methods=["GET","POST"])
def password_reset(token):
    con = db(); c = con.cursor()
    u = c.execute("SELECT id, reset_token_exp FROM users WHERE reset_token=?", (token,)).fetchone()
    if not u:
        con.close(); flash("Token نادروستە یان بەسەرچووە."); return redirect(url_for("password_forgot"))
    try:
        exp = datetime.strptime(u["reset_token_exp"], "%Y-%m-%d %H:%M:%S")
    except Exception:
        exp = datetime.utcnow() - timedelta(seconds=1)
    if datetime.utcnow() > exp:
        c.execute("UPDATE users SET reset_token=NULL, reset_token_exp=NULL WHERE id=?", (u["id"],))
        con.commit(); con.close()
        flash("Token بەسەرچووە، دووبارە هەوڵبدە.")
        return redirect(url_for("password_forgot"))
    if request.method == "POST":
        p1 = request.form.get("password","") or ""
        p2 = request.form.get("password2","") or ""
        ok, msg = validate_password(p1, p2)
        if not ok:
            flash(msg, "error")
            return redirect(url_for("password_reset", token=token))
        c.execute("UPDATE users SET password_hash=?, reset_token=NULL, reset_token_exp=NULL WHERE id=?",
                  (generate_password_hash(p1), u["id"]))
        con.commit(); con.close()
        flash("پاسۆرد نوێکرایەوە. ئێستا دەتوانی بچیتە ژوورەوە.")
        return redirect(url_for("login"))
    con.close()
    return render_template("auth_reset.html")

# ------------ API v1: Auth (token) ------------
@app.route("/api/v1/auth/token", methods=["POST"]) 
def api_auth_token():
    # accept JSON or form
    if request.is_json:
        data = request.get_json(silent=True) or {}
        user_or_email = (data.get("user_or_email","") or "").strip().lower()
        password = data.get("password","") or ""
    else:
        user_or_email = (request.form.get("user_or_email","") or "").strip().lower()
        password = request.form.get("password","") or ""

    if not user_or_email or not password:
        return api_json(False, error="user_or_email و password پێویستن.", status=400)

    con = db(); c = con.cursor()
    u = c.execute("SELECT * FROM users WHERE username=? OR email=?", (user_or_email, user_or_email)).fetchone()
    con.close()
    if not u or not check_password_hash(u["password_hash"], password):
        return api_json(False, error="ناسنامە یان پاسۆرد هەڵە.", status=401)
    if not (u["email_verified"] or 0):
        return api_json(False, error="ئیمەیڵ سەلمێندرانی نییە.", status=403)

    tok, exp = _issue_api_token(u["id"])
    return api_json(True, data={"token": tok, "expires_at": exp})

# ------------ API v1: Upload (image/file) ------------
@app.route("/api/v1/uploads", methods=["POST"]) 
@api_auth_required
def api_upload():
    if "file" not in request.files:
        return api_json(False, error="file پێویستە", status=400)
    try:
        url = save_uploaded_file(request.files["file"])
        return api_json(True, data={"url": url})
    except ValueError as e:
        return api_json(False, error=str(e), status=400)

# ------------ API v1: Pages (public + admin CRUD) ------------
# Public read
@app.route("/api/v1/pages/<slug>", methods=["GET"]) 
def api_pages_public_get(slug):
    con = db(); c = con.cursor()
    p = c.execute("SELECT slug,title,html,updated_at FROM pages WHERE slug=?", (slug,)).fetchone()
    con.close()
    if not p:
        return api_json(False, error="Not found", status=404)
    return api_json(True, data={"slug": p["slug"], "title": p["title"], "html": p["html"], "updated_at": p["updated_at"]})

# Admin list
@app.route("/api/v1/admin/pages", methods=["GET"]) 
@api_auth_required
@api_admin_required
def api_pages_list():
    con = db(); c = con.cursor()
    rows = c.execute("SELECT slug,title,updated_at FROM pages ORDER BY updated_at DESC").fetchall()
    con.close()
    items = [{"slug": r["slug"], "title": r["title"], "updated_at": r["updated_at"]} for r in rows]
    return api_json(True, data={"items": items})

# Admin create
@app.route("/api/v1/admin/pages", methods=["POST"]) 
@api_auth_required
@api_admin_required
def api_pages_create():
    data = request.get_json(silent=True) or request.form
    title = (data.get("title") or "").strip()
    html  = (data.get("html") or "").strip()
    slug  = slugify((data.get("slug") or title))
    if not title or not html:
        return api_json(False, error="title و html پێویستن.", status=400)
    con = db(); c = con.cursor()
    try:
        c.execute("INSERT INTO pages(slug,title,html) VALUES (?,?,?)", (slug, title, html))
        con.commit()
    except sqlite3.IntegrityError:
        con.rollback(); con.close()
        return api_json(False, error="slug پێشتر هەیە.", status=409)
    p = c.execute("SELECT slug,title,html,updated_at FROM pages WHERE slug=?", (slug,)).fetchone()
    con.close()
    return api_json(True, data={"slug": p["slug"], "title": p["title"], "html": p["html"], "updated_at": p["updated_at"]}, status=201)

# Admin update
@app.route("/api/v1/admin/pages/<slug>", methods=["PATCH"]) 
@api_auth_required
@api_admin_required
def api_pages_update(slug):
    data = request.get_json(silent=True) or request.form
    title = data.get("title")
    html  = data.get("html")
    con = db(); c = con.cursor()
    exists = c.execute("SELECT 1 FROM pages WHERE slug=?", (slug,)).fetchone()
    if not exists:
        con.close(); return api_json(False, error="Not found", status=404)
    cols, vals = [], []
    if title is not None:
        cols.append("title=?"); vals.append(title.strip())
    if html is not None:
        cols.append("html=?"); vals.append(html)
    if not cols:
        con.close(); return api_json(True, data={"updated": False})
    cols.append("updated_at=CURRENT_TIMESTAMP")
    q = f"UPDATE pages SET {', '.join(cols)} WHERE slug=?"
    vals.append(slug)
    c.execute(q, tuple(vals))
    con.commit()
    p = c.execute("SELECT slug,title,html,updated_at FROM pages WHERE slug=?", (slug,)).fetchone()
    con.close()
    return api_json(True, data={"slug": p["slug"], "title": p["title"], "html": p["html"], "updated_at": p["updated_at"]})

# Admin delete
@app.route("/api/v1/admin/pages/<slug>", methods=["DELETE"]) 
@api_auth_required
@api_admin_required
def api_pages_delete(slug):
    con = db(); c = con.cursor()
    row = c.execute("SELECT 1 FROM pages WHERE slug=?", (slug,)).fetchone()
    if not row:
        con.close(); return api_json(False, error="Not found", status=404)
    c.execute("DELETE FROM pages WHERE slug=?", (slug,))
    con.commit(); con.close()
    return api_json(True, data={"deleted": slug})

# Quick who-am-I
@app.route("/api/v1/me", methods=["GET"]) 
@api_auth_required
def api_me():
    u = request.api_user
    return api_json(True, data={"id": u["id"], "username": u["username"], "email": u["email"], "is_admin": bool(u["is_admin"])})

# ------------ API v1: Posts ------------
@app.route("/api/v1/posts", methods=["GET"]) 
def api_posts_public_list():
    page = max(int(request.args.get("page", 1) or 1), 1)
    per  = min(max(int(request.args.get("per_page", 20) or 20), 1), 100)
    off  = (page - 1) * per

    con = db(); c = con.cursor()
    rows = c.execute("""SELECT * FROM posts WHERE is_published=1
                        ORDER BY id DESC LIMIT ? OFFSET ?""", (per, off)).fetchall()
    total = c.execute("SELECT COUNT(*) FROM posts WHERE is_published=1").fetchone()[0]
    con.close()
    data = [row_to_post_dict(r) for r in rows]
    return api_json(True, data={"items": data, "page": page, "per_page": per, "total": total})

@app.route("/api/v1/posts/<int:pid>", methods=["GET"]) 
def api_posts_public_get(pid):
    con = db(); c = con.cursor()
    r = c.execute("SELECT * FROM posts WHERE id=?", (pid,)).fetchone()
    con.close()
    if not r or not r["is_published"]:
        return api_json(False, error="Not found", status=404)
    return api_json(True, data=row_to_post_dict(r))

@app.route("/api/v1/my/posts", methods=["GET"]) 
@api_auth_required
def api_my_posts():
    page = max(int(request.args.get("page", 1) or 1), 1)
    per  = min(max(int(request.args.get("per_page", 20) or 20), 1), 100)
    off  = (page - 1) * per

    uid = request.api_user["id"]
    con = db(); c = con.cursor()
    rows = c.execute("""SELECT * FROM posts WHERE user_id=? ORDER BY id DESC
                        LIMIT ? OFFSET ?""", (uid, per, off)).fetchall()
    total = c.execute("SELECT COUNT(*) FROM posts WHERE user_id=?", (uid,)).fetchone()[0]
    con.close()
    data = [row_to_post_dict(r) for r in rows]
    return api_json(True, data={"items": data, "page": page, "per_page": per, "total": total})

@app.route("/api/v1/posts", methods=["POST"]) 
@api_auth_required
def api_posts_create():
    uid = request.api_user["id"]

    # Read inputs from multipart or JSON
    if request.files or (request.form and not request.is_json):
        title = request.form.get("title")
        body  = request.form.get("body")
        is_pub= request.form.get("is_published")
        try:
            img_url = save_uploaded_file(request.files.get("image")) if "image" in request.files else None
        except ValueError as e:
            return api_json(False, error=str(e), status=400)
    else:
        js = request.get_json(silent=True) or {}
        title = js.get("title")
        body  = js.get("body")
        is_pub= js.get("is_published")
        img_url = js.get("image_url")

    if not title or not str(title).strip():
        return api_json(False, error="title پێویستە.", status=400)

    is_published = 1 if str(is_pub).lower() in ("1","true","yes","on") else 0

    con = db(); c = con.cursor()
    c.execute("""INSERT INTO posts(user_id,title,body,image_url,is_published)
                 VALUES (?,?,?,?,?)""", (uid, title.strip(), (body or "").strip(), img_url, is_published))
    pid = c.lastrowid
    con.commit()
    r = c.execute("SELECT * FROM posts WHERE id=?", (pid,)).fetchone()
    con.close()
    return api_json(True, data=row_to_post_dict(r), status=201)

@app.route("/api/v1/my/posts/<int:pid>", methods=["PATCH"]) 
@api_auth_required
def api_posts_update(pid):
    uid = request.api_user["id"]
    con = db(); c = con.cursor()
    r = c.execute("SELECT * FROM posts WHERE id=?", (pid,)).fetchone()
    if not r:
        con.close(); return api_json(False, error="Not found", status=404)
    if (r["user_id"] != uid) and (not request.api_user["is_admin"]):
        con.close(); return api_json(False, error="Forbidden", status=403)

    # Read inputs from multipart or JSON
    if request.files or (request.form and not request.is_json):
        title = request.form.get("title")
        body  = request.form.get("body")
        is_pub = request.form.get("is_published")
        try:
            new_img = save_uploaded_file(request.files.get("image")) if "image" in request.files else None
        except ValueError as e:
            con.close(); return api_json(False, error=str(e), status=400)
    else:
        js = request.get_json(silent=True) or {}
        title = js.get("title")
        body  = js.get("body")
        is_pub= js.get("is_published")
        new_img = js.get("image_url")

    cols, vals = [], []
    if title is not None:
        cols.append("title=?"); vals.append(title.strip())
    if body is not None:
        cols.append("body=?"); vals.append(body.strip())
    if is_pub is not None:
        cols.append("is_published=?"); vals.append(1 if str(is_pub).lower() in ("1","true","yes","on") else 0)
    if new_img:
        cols.append("image_url=?"); vals.append(new_img)

    if cols:
        cols.append("updated_at=CURRENT_TIMESTAMP")
        q = f"UPDATE posts SET {', '.join(cols)} WHERE id=?"
        vals.append(pid)
        c.execute(q, tuple(vals))
        con.commit()

    r2 = c.execute("SELECT * FROM posts WHERE id=?", (pid,)).fetchone()
    con.close()
    return api_json(True, data=row_to_post_dict(r2))

@app.route("/api/v1/my/posts/<int:pid>", methods=["DELETE"]) 
@api_auth_required
def api_posts_delete(pid):
    uid = request.api_user["id"]
    con = db(); c = con.cursor()
    r = c.execute("SELECT user_id FROM posts WHERE id=?", (pid,)).fetchone()
    if not r:
        con.close(); return api_json(False, error="Not found", status=404)
    if (r["user_id"] != uid) and (not request.api_user["is_admin"]):
        con.close(); return api_json(False, error="Forbidden", status=403)
    c.execute("DELETE FROM posts WHERE id=?", (pid,))
    con.commit(); con.close()
    return api_json(True, data={"deleted": pid})
@app.route('/api/payout/provider/<int:pid>/fields')
def payout_provider_fields(pid):
    con = db(); c = con.cursor()
    p = c.execute("SELECT fields_json FROM payout_providers WHERE id=? AND is_active=1", (pid,)).fetchone()
    con.close()
    return jsonify(json.loads(p['fields_json'] or "{}")) if p else jsonify({})

# ------------ Public pages ------------
@app.route("/")
def index():
    con = db(); c = con.cursor()
    active_surveys = c.execute("SELECT id,title,description,reward_points FROM surveys WHERE is_active=1 ORDER BY id DESC LIMIT 6").fetchall()
    active_ads     = c.execute("SELECT id,title,image_url,link_url FROM ads WHERE is_active=1 ORDER BY id DESC LIMIT 6").fetchall()
    con.close()
    return render_template("home.html", surveys=active_surveys, ads=active_ads)

@app.route("/surveys")
def surveys_page():
    con = db(); c = con.cursor()
    rows = c.execute("SELECT id,title,description,is_active,reward_points,created_at FROM surveys ORDER BY id DESC").fetchall()
    con.close()
    return render_template("surveys.html", rows=rows)
from flask import Response
import io, csv

@app.route("/surveys/<int:survey_id>", methods=["GET","POST"])
@login_required
def survey_take(survey_id):
    con = db(); c = con.cursor()
    s = c.execute("SELECT * FROM surveys WHERE id=? AND is_active=1", (survey_id,)).fetchone()
    if not s:
        con.close(); abort(404)

    qs = c.execute("SELECT * FROM survey_questions WHERE survey_id=? ORDER BY id", (survey_id,)).fetchall()

    if request.method == "POST":
        # تۆمارکردنی سەلماندن
        c.execute("INSERT INTO survey_submissions(survey_id, user_id) VALUES (?,?)",
                  (survey_id, session.get("user_id")))
        sub_id = c.lastrowid

        # هەر پرسیارێک: q_<id>
        for q in qs:
            field = f"q_{q['id']}"
            if q["q_type"] == "multi":
                vals = request.form.getlist(field)  # چەند هەڵبژاردە
                ans = "|".join(v.strip() for v in vals if v.strip())
            else:
                ans = (request.form.get(field) or "").strip()
            c.execute("""INSERT INTO survey_answers(submission_id, question_id, answer_text)
                         VALUES (?,?,?)""", (sub_id, q["id"], ans))
        con.commit(); con.close()
        flash("سوپاس! وەڵامەکانت تۆمار کران.")
        return redirect(url_for("home"))

    con.close()
    # قالیبەکە هەبوو؟ هەمانە بەکاربهێنە—نەبوو فۆڵبەک HTML
    try:
        return render_template("survey_take.html", s=s, qs=qs)
    except Exception:
        # فۆڵبەک: فورمی سادە
        def input_for(q):
            name = f"q_{q['id']}"
            t = q["q_type"]
            opts = (q["q_options"] or "").split("|") if q["q_options"] else []
            if t == "single":
                return "<br>".join([f"<label><input type='radio' name='{name}' value='{o.strip()}'> {o.strip()}</label>" for o in opts])
            if t == "multi":
                return "<br>".join([f"<label><input type='checkbox' name='{name}' value='{o.strip()}'> {o.strip()}</label>" for o in opts])
            if t == "number":
                return f"<input type='number' name='{name}' step='1'>"
            return f"<input type='text' name='{name}'>"

        items = "".join([f"<div style='margin:12px 0'><b>{q['q_text']}</b><div>{input_for(q)}</div></div>" for q in qs]) or "<p>هیچ پرسیارێک نییە.</p>"
        return f"""<!doctype html><meta charset='utf-8'>
        <h3 style="font-family:system-ui">{s['title']}</h3>
        <form method="post">{items}<button>ناردن</button></form>"""
@app.route("/admin/surveys/<int:survey_id>/results")
@admin_required
def admin_survey_results(survey_id):
    con = db(); c = con.cursor()
    s = c.execute("SELECT * FROM surveys WHERE id=?", (survey_id,)).fetchone()
    if not s: con.close(); abort(404)

    qs = c.execute("SELECT * FROM survey_questions WHERE survey_id=? ORDER BY id", (survey_id,)).fetchall()

    # هەڵبژاردنەکان/ژمارەکردن
    results = []
    for q in qs:
        qid = q["id"]; qtype = q["q_type"]
        rows = c.execute("SELECT answer_text FROM survey_answers sa JOIN survey_submissions ss ON ss.id=sa.submission_id WHERE ss.survey_id=? AND sa.question_id=?", (survey_id, qid)).fetchall()
        values = [ (r["answer_text"] or "").strip() for r in rows ]

        summary = {"question": q, "type": qtype}

        if qtype in ("single", "multi"):
            # کۆمەڵەکردنی هەڵبژاردنەکان
            from collections import Counter
            if qtype == "multi":
                flat = []
                for v in values:
                    if v:
                        flat.extend([x.strip() for x in v.split("|") if x.strip()])
                counts = Counter(flat)
            else:
                counts = Counter([v for v in values if v])
            summary["counts"] = counts
            summary["total"] = sum(counts.values())
        elif qtype == "number":
            nums = []
            for v in values:
                try:
                    nums.append(float(v))
                except Exception:
                    pass
            summary["stats"] = {
                "count": len(nums),
                "avg": (sum(nums)/len(nums)) if nums else None,
                "min": min(nums) if nums else None,
                "max": max(nums) if nums else None,
            }
        else:
            # text — تەنیا نمونەی ٥٠ هێنانە
            summary["samples"] = values[:50]

        results.append(summary)

    total_subs = c.execute("SELECT COUNT(*) AS n FROM survey_submissions WHERE survey_id=?", (survey_id,)).fetchone()["n"]
    con.close()

    try:
        return render_template("admin_survey_results.html", s=s, results=results, total_subs=total_subs)
    except Exception:
        # فۆڵبەک HTML
        parts = [f"<h3 style='font-family:system-ui'>ئەنجامەکان — {s['title']} (کۆی وەڵام: {total_subs})</h3>"]
        for item in results:
            q = item["question"]
            parts.append(f"<div style='margin:16px 0'><b>• {q['q_text']}</b> <small>({q['q_type']})</small><br>")
            if item["type"] in ("single","multi"):
                if item.get("counts"):
                    for opt, cnt in item["counts"].most_common():
                        parts.append(f"{opt or '(خالی)'} — {cnt}<br>")
                else:
                    parts.append("هیچ وەڵامێک نییە.")
            elif item["type"] == "number":
                st = item["stats"]
                parts.append(f"Count={st['count']} | Avg={st['avg']} | Min={st['min']} | Max={st['max']}")
            else:
                smp = item.get("samples") or []
                if smp:
                    parts.append("<ul>" + "".join([f"<li>{v}</li>" for v in smp]) + "</ul>")
                else:
                    parts.append("هیچ وەڵامێک نییە.")
            parts.append("</div>")
        return "<!doctype html><meta charset='utf-8'>" + "".join(parts)
@app.route("/admin/surveys/<int:survey_id>/export.csv")
@admin_required
def admin_survey_export_csv(survey_id):
    con = db(); c = con.cursor()
    # بە شێوەی «row per answer»
    rows = c.execute("""
        SELECT ss.id AS submission_id,
               ss.user_id,
               ss.submitted_at,
               q.id AS question_id,
               q.q_text,
               q.q_type,
               sa.answer_text FROM survey_submissions ss
        JOIN survey_answers sa ON sa.submission_id = ss.id
        JOIN survey_questions q ON q.id = sa.question_id
        WHERE ss.survey_id=?
        ORDER BY ss.id, q.id
    """, (survey_id,)).fetchall()
    con.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["submission_id", "user_id", "submitted_at", "question_id", "q_text", "q_type", "answer_text"])
    for r in rows:
        writer.writerow([r["submission_id"], r["user_id"], r["submitted_at"], r["question_id"], r["q_text"], r["q_type"], r["answer_text"]])

    data = output.getvalue().encode("utf-8-sig")
    return Response(data, mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="survey_{survey_id}_export.csv"'})

@app.route("/research")
def research_page():
    return render_template("research.html")

@app.route("/stats")
def stats_page():
    con = db(); c = con.cursor()
    counts = {
        "users":   c.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "surveys": c.execute("SELECT COUNT(*) FROM surveys").fetchone()[0],
        "answers": c.execute("SELECT COUNT(*) FROM survey_response_items").fetchone()[0],
        "ads":     c.execute("SELECT COUNT(*) FROM ads").fetchone()[0],
        "games":   c.execute("SELECT COUNT(*) FROM games").fetchone()[0],
    }
    con.close()
    return render_template("stats.html", counts=counts)

@app.route("/archive")
def archive_page():
    return render_template("archive.html")

@app.route("/ads")
def ads_page():
    con = db(); c = con.cursor()
    rows = c.execute("SELECT * FROM ads WHERE is_active=1 ORDER BY id DESC").fetchall()
    con.close()
    return render_template("ads.html", rows=rows)

@app.route("/games")
def games_page():
    con = db(); c = con.cursor()
    rows = c.execute("SELECT * FROM games WHERE is_active=1 ORDER BY id DESC").fetchall()
    con.close()
    return render_template("games.html", rows=rows)

@app.route("/about")
def about_page():
    con = db(); c = con.cursor()
    p = c.execute("SELECT * FROM pages WHERE slug='about'").fetchone()
    con.close()
    if p: return render_template("page_dynamic.html", page=p)
    return render_template("about.html")

@app.route("/contact")
def contact_page():
    con = db(); c = con.cursor()
    p = c.execute("SELECT * FROM pages WHERE slug='contact'").fetchone()
    con.close()
    if p: return render_template("page_dynamic.html", page=p)
    return render_template("contact.html")

@app.route("/p/<slug>")
def page_by_slug(slug):
    con = db(); c = con.cursor()
    p = c.execute("SELECT * FROM pages WHERE slug=?", (slug,)).fetchone()
    con.close()
    if not p: abort(404)
    return render_template("page_dynamic.html", page=p)
# PATCH: ڕێکخستنی بنەڕەتی یاری (Only if missing)
if 'admin_games_earn_settings' not in app.view_functions:
    @app.route("/admin/games-earn-settings", methods=["GET","POST"])
    @admin_required
    def admin_games_earn_settings():
        if request.method == "POST":
            try:
                set_setting("games_daily_quota", max(0, int(request.form.get("games_daily_quota") or "10")))
                set_setting("games_points_per_play", max(0, int(request.form.get("games_points_per_play") or "5")))
                set_setting("games_min_seconds", max(0, int(request.form.get("games_min_seconds") or "30")))
            except ValueError:
                flash("تکایە ژمارەی دروست بنووسە.")
                return redirect(url_for("admin_games_earn_settings"))
            flash("پاشەکەوت کرا.")
            return redirect(url_for("admin_games_earn_settings"))
        data = {
            "games_daily_quota": get_setting("games_daily_quota", "10"),
            "games_points_per_play": get_setting("games_points_per_play", "5"),
            "games_min_seconds": get_setting("games_min_seconds", "30"),
        }
        # قاڵب هەبوو بەکارهێنە، نەبوو fallback
        try:
            return render_template("admin_games_earn_settings.html", data=data)
        except Exception:
            return f"""<!doctype html><meta charset='utf-8'>
            <h2 style="font-family:system-ui">Game Earn Settings</h2>
            <form method="post">
              <div>کۆتایی ڕۆژانە: <input type="number" name="games_daily_quota" value="{data['games_daily_quota']}"></div>
              <div>پۆینت/یاری: <input type="number" name="games_points_per_play" value="{data['games_points_per_play']}"></div>
              <div>کەمترین چرکە: <input type="number" name="games_min_seconds" value="{data['games_min_seconds']}"></div>
              <button>Save</button>
            </form>"""
@app.post('/wallet/payout')
@login_required
def wallet_payout_post():
    uid = session['user_id']
    con = db(); c = con.cursor()

    # settings
    get = lambda k, d='0': (c.execute("SELECT value FROM app_settings WHERE key=?", (k,)).fetchone() or {'value':d})['value']
    min_pts = int(get('min_payout_points','100'))
    fee_pts = int(get('payout_fee_points','5'))

    # input & validate
    provider_id = int(request.form.get('provider_id') or 0)
    points = int(request.form.get('points') or 0)
    if points < min_pts: return flash("کەمترە لە کەمترین پۆینت"), redirect(url_for('wallet_payout'))

    prof = c.execute("SELECT wallet_points FROM profiles WHERE id=?", (uid,)).fetchone()
    if not prof: abort(400)
    need = points + fee_pts
    if (prof['wallet_points'] or 0) < need:
        return flash("پۆینتەکانت ناتەواون"), redirect(url_for('wallet_payout'))

    # provider & fields
    prov = c.execute("SELECT id,fields_json,name,kind FROM payout_providers WHERE id=? AND is_active=1",(provider_id,)).fetchone()
    if not prov: return flash("سەرچاوە نەدۆزرایەوە"), redirect(url_for('wallet_payout'))
    fields = json.loads(prov['fields_json'] or "{}")

    # build account_json from posted acc_* keys with validation
    account = {}
    for key, spec in fields.items():
        val = (request.form.get(f'acc_{key}') or '').strip()
        if spec.get('required') and not val:
            return flash(f"خانە {key} پڕبکەوە"), redirect(url_for('wallet_payout'))
        pat = spec.get('pattern')
        if pat:
            import re
            if val and not re.match(pat, val):
                return flash(f"نرخی {key} نادروستە"), redirect(url_for('wallet_payout'))
        account[key] = val

    # create or update user_payout_methods (default)
    c.execute("""INSERT INTO user_payout_methods(user_id, provider_id, account_json, is_default, status)
                 VALUES(?,?,?,?,?)""", (uid, provider_id, json.dumps(account), 1, 'unverified'))

    # create payout request (pending)
    c.execute("""INSERT INTO payout_requests(user_id, method, provider, account, points, fee_points, status, created_at)
                 VALUES(?,?,?,?,?,?, 'pending', datetime('now'))""",
              (uid, prov['kind'], prov['name'], account.get('mobile') or account.get('iban') or json.dumps(account),
               points, fee_pts))

    con.commit(); con.close()
    flash("داواکاری پارەدان پێشکەش کرا. دەمەزرێندرێت لەلایەن ئەدمین.")
    return redirect(url_for('wallet_payout'))
@app.post('/admin/payouts/mark_paid')
@admin_required
def admin_payout_mark_paid():
    pid = int(request.form.get('pid') or 0)
    con = db(); c = con.cursor()
    r = c.execute("SELECT user_id, points, fee_points, status FROM payout_requests WHERE id=?", (pid,)).fetchone()
    if not r: abort(404)
    if r['status'] == 'paid':
        flash("ئەم پەیدانە پێشتر paid بوو"); return redirect(url_for('admin_payouts'))

    need = int(r['points'] or 0) + int(r['fee_points'] or 0)
    bal = c.execute("SELECT wallet_points FROM profiles WHERE user_id=?", (r['user_id'],)).fetchone()['wallet_points'] or 0
    if bal < need:
        flash("پۆینتی بەکارهێنەر کەمە بۆ پەیدان"); return redirect(url_for('admin_payouts'))

    # deduct & mark paid
    c.execute("UPDATE profiles SET wallet_points = wallet_points - ? WHERE id=?", (need, r['user_id']))
    c.execute("INSERT INTO wallet_transactions(user_id, change, type, source, note, created_at) VALUES (?,?,?,?,?,datetime('now'))",
              (r['user_id'], -need, 'payout', 'payout', f'payout #{pid}'))
    c.execute("UPDATE payout_requests SET status='paid', processed_at=datetime('now') WHERE id=?", (pid,))
    con.commit(); con.close()
    flash("پەیدان تەواو کرا ✓")
    return redirect(url_for('admin_payouts'))

# ---- Rewards: Ads (once per day) ----
@app.route("/ads/<int:ad_id>/go")
def ad_go(ad_id):
    con = db(); c = con.cursor()
    ad = c.execute("SELECT * FROM ads WHERE id=? AND is_active=1", (ad_id,)).fetchone()
    if not ad:
        con.close()
        flash("ڕێکلام نەدۆزرایەوە یان ناچالاکە.")
        return redirect(url_for("ads_page"))

    if session.get("user_id"):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        row = c.execute("SELECT 1 FROM ad_views WHERE user_id=? AND ad_id=? AND day=?",
                        (session["user_id"], ad_id, today)).fetchone()
        if not row:
            c.execute("INSERT INTO ad_views(user_id,ad_id,day) VALUES (?,?,?)",
                      (session["user_id"], ad_id, today))
            con.commit()
            # پۆینتی تایبەتی بەو ڕێکلامە بەکار بهێنە، ئەگەر نەبوو پۆینتی گشتی بەکار بهێنە
            pts = int(ad["reward_points"] or get_setting("pts_ad_view","2"))
            con.close()
            add_points(session["user_id"], pts, f"بینینی ڕێکلام #{ad_id}", "earn")
            flash(f"بەهرەت بەدەست هێنا: {pts} پۆینت")
        else:
            con.close()
            flash("تۆ ئەمڕۆ ئەم ڕێکلامەت بینیوە.")
    else:
        con.close()

    link = ad["link_url"] or url_for("ads_page")
    return redirect(link)
# ---- Rewards: Games (once per day) ----
@app.route("/games/<int:game_id>/play")
def game_play(game_id):
    con = db(); c = con.cursor()
    g = c.execute("SELECT * FROM games WHERE id=? AND is_active=1", (game_id,)).fetchone()
    if not g:
        con.close()
        flash("یاری نەدۆزرایەوە یان ناچالاکە.")
        return redirect(url_for("games_page"))

    awarded = False
    if session.get("user_id"):
        today = datetime.utcnow().strftime("%Y-%m-%d")
        row = c.execute("SELECT 1 FROM game_plays WHERE user_id=? AND game_id=? AND day=?",
                        (session["user_id"], game_id, today)).fetchone()
        if not row:
            c.execute("INSERT INTO game_plays(user_id,game_id,day) VALUES (?,?,?)",
                      (session["user_id"], game_id, today))
            con.commit()
            pts = int(get_setting("pts_game_play","5"))
            con.close()
            add_points(session["user_id"], pts, f"یاری‌کردن #{game_id}", "earn")
            awarded = True
        else:
            con.close()

    return render_template("game_play.html", game=g, awarded=awarded)

# ------------ Profile core + packages (dynamic) ------------
@app.route("/profile", methods=["GET","POST"]) 
@login_required
def profile():
    # helper to read option lists (with defaults)
    def get_list_setting(key, default_list):
        try:
            raw = get_setting(key)
            if raw:
                arr = json.loads(raw)
                if isinstance(arr, list): return arr
        except Exception: pass
        return default_list

    defaults = {
      "degrees": ["بێ بڕوانامە","سەرەتایی","ناوەندی","ئامادەیی","دبلۆم","بكالۆریۆس","دبلۆمی باڵا","ماستەر","دكتۆرا"],
      "cities": ["هەولێر","سلێمانی","دهۆک","کەرکوک","مووسڵ","بەغداد","بەصرە","نەجەف","کەربەلا"],
      "famstat": ["خێزاندار","سەڵت","جیابووەوە","نەمانی هاوسەر"],
      "work_types": ["حکومی","ئەهلی","سەربەخۆ","رێکخراوەیی","حزبی","هیتر"],
    }

    if request.method == "POST":
        con = db(); c = con.cursor()
        full_name  = request.form.get("full_name"," ").strip()
        middle_name= request.form.get("middle_name"," ").strip()
        nickname   = request.form.get("nickname"," ").strip()
        gender     = request.form.get("gender"," ").strip()
        phone_code = request.form.get("phone_code"," ").strip()
        phone      = re.sub(r"[^\d]","", request.form.get("phone","") or "")
        age_val    = request.form.get("age"," ").strip()
        age        = int(age_val) if age_val.isdigit() else None
        degree     = request.form.get("degree"," ").strip()
        city       = request.form.get("city"," ").strip()
        family_status = request.form.get("family_status"," ").strip()
        work_type  = request.form.get("work_type"," ").strip()
        political_member = request.form.get("political_member"," ").strip()
        c.execute("""
          UPDATE profiles
          SET full_name=?, middle_name=?, nickname=?, gender=?, phone_code=?, phone=?, age=?, degree=?, city=?, family_status=?, work_type=?, political_member=?, updated_at=CURRENT_TIMESTAMP
          WHERE user_id=?
        """, (full_name, middle_name, nickname, gender, phone_code, phone, age, degree, city, family_status, work_type, political_member, session["user_id"]))
        con.commit(); con.close()
        flash("پڕۆفایل نوێکرایەوە.")

    con = db(); c = con.cursor()
    p = c.execute("SELECT * FROM profiles WHERE user_id=?", (session["user_id"],)).fetchone()
    pkgs = c.execute("SELECT code, title, position FROM profile_packages ORDER BY position, code").fetchall()
    comp = c.execute("SELECT section FROM profile_details WHERE user_id=?", (session["user_id"],)).fetchall()
    con.close()
    completed_codes = {row["section"] for row in comp}
    pkg_states = [{"code":x["code"],"title":x["title"],"position":x["position"],"done":(x["code"] in completed_codes)} for x in pkgs]

    # Build options for dropdowns
    opts = {
        "opt_degrees": get_list_setting("opt_degrees", defaults["degrees"]),
        "opt_cities": get_list_setting("opt_cities", defaults["cities"]),
        "opt_famstat": get_list_setting("opt_famstat", defaults["famstat"]),
        "opt_work_types": get_list_setting("opt_work_types", defaults["work_types"]),
        "opt_genders": ["نێر","مێ"],
        "opt_ages": [str(n) for n in range(15, 81)],
    }

    return render_template("profile.html", p=p, pkg_states=pkg_states, opts=opts)

# alias for old links if any
@app.route("/profile/setup") 
@login_required
def profile_setup():
    return redirect(url_for("profile"))

def _award_and_snapshot(user_id, code, payload_dict):
    pts = int(get_setting("pts_profile_section","20"))
    con = db(); c = con.cursor()
    row = c.execute("SELECT awarded_points FROM profile_details WHERE user_id=? AND section=?", (user_id, code)).fetchone()
    if row:
        c.execute("UPDATE profile_details SET payload_json=?, updated_at=CURRENT_TIMESTAMP WHERE user_id=? AND section=?",
                  (json.dumps(payload_dict, ensure_ascii=False), user_id, code))
        awarded = row["awarded_points"] or 0
    else:
        c.execute("INSERT INTO profile_details(user_id,section,payload_json,awarded_points) VALUES (?,?,?,?)",
                  (user_id, code, json.dumps(payload_dict, ensure_ascii=False), pts))
        awarded = 0
    con.commit(); con.close()
    if not row or awarded == 0:
        add_points(user_id, pts, f"پڕکردنەوەی پاکێجی پڕۆفایل: {code}", "earn")

@app.route("/profile/sections/<code>", methods=["GET","POST"]) 
@login_required
def profile_sec_dynamic(code):
    con = db(); c = con.cursor()
    pkg = c.execute("SELECT * FROM profile_packages WHERE code=?", (code,)).fetchone()
    if not pkg: con.close(); abort(404)
    qs_db = c.execute("SELECT * FROM profile_questions WHERE pkg_code=? ORDER BY position,id", (code,)).fetchall()
    questions = []
    for q in qs_db:
        opts = []
        if q["options_json"]:
            try: opts = json.loads(q["options_json"]) 
            except: opts = []
        questions.append({**dict(q), "options": opts})

    ans_rows = c.execute("SELECT question_id, answer_text FROM profile_answers WHERE user_id=? AND pkg_code=?", (session["user_id"], code)).fetchall()
    answers = {f"q_{r['question_id']}": r["answer_text"] for r in ans_rows}

    if request.method == "POST":
        c.execute("DELETE FROM profile_answers WHERE user_id=? AND pkg_code=?", (session["user_id"], code))
        payload = {}
        for q in questions:
            name = f"q_{q['id']}"
            qt = q["q_type"]
            val = ", ".join(request.form.getlist(name)) if qt=="checkbox" else request.form.get(name,"").strip()
            c.execute("INSERT INTO profile_answers(user_id,pkg_code,question_id,answer_text) VALUES (?,?,?,?)",
                      (session["user_id"], code, q["id"], val))
            payload[str(q["id"])] = val
        con.commit(); con.close()
        _award_and_snapshot(session["user_id"], code, payload)
        flash("پاکێج پاشەکەوت کرا.")
        return redirect(url_for("profile"))
    con.close()
    return render_template("profile_section_dynamic.html", package=pkg, questions=questions, answers=answers)

# ------------ Wallet/Payout ------------
@app.route("/wallet", methods=["GET","POST"]) 
@login_required
def wallet():
    con = db(); c = con.cursor()
    prof = c.execute("SELECT wallet_points FROM profiles WHERE user_id=?", (session["user_id"],)).fetchone()
    tx   = c.execute("SELECT * FROM wallet_transactions WHERE user_id=? ORDER BY id DESC LIMIT 100", (session["user_id"],)).fetchall()
    balance = prof["wallet_points"] if prof else 0
    if request.method == "POST":
        method   = request.form.get("method")
        provider = request.form.get("provider","").strip()
        account  = request.form.get("account","").strip()
        pts      = int(request.form.get("points") or 0)
        min_pts  = int(get_setting("min_payout_points","100"))
        if pts <= 0 or pts > balance or pts < min_pts:
            con.close(); flash("ژمارەی پۆینت نادروستە یان کەمترە لە نۆرم."); return redirect(url_for("wallet"))
        money_per = int(get_setting("money_per_point","10"))
        money_cents = pts * money_per
        con.close()
        add_points(session["user_id"], -pts, "پێشنیازی پارەدان", "spend")
        con = db(); c = con.cursor()
        c.execute("""INSERT INTO payout_requests(user_id,method,provider,account,points,money_cents,status)
                     VALUES (?,?,?,?,?,?, 'pending')""",
                  (session["user_id"], method, provider, account, pts, money_cents))
        con.commit(); con.close()
        flash("داواکاری پارەدان نێردرا (pending).")
        return redirect(url_for("wallet"))
    con.close()
    providers_bank = ["FIB","CBI","TradeBank","ZiP","HiTR"]
    providers_mobile = ["FastPay","NaxPay","ZainCash","AsiaHawala"]
    return render_template("wallet.html", balance=balance, tx=tx, providers_bank=providers_bank, providers_mobile=providers_mobile)

# ------------ Admin Dashboard ------------
@app.route("/admin") 
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html")

# ------------ Admin: CMS Pages ------------
@app.route("/admin/pages")
@admin_required
def admin_pages():
    con = db(); c = con.cursor()
    rows = c.execute("SELECT slug,title,updated_at FROM pages ORDER BY updated_at DESC").fetchall()
    con.close()
    return render_template("admin_pages.html", rows=rows)

@app.route("/admin/pages/new", methods=["GET","POST"])
@admin_required
def admin_page_new():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        slug_in = (request.form.get("slug") or "").strip().lower()
        html = (request.form.get("html") or "").strip()   # ⭐ ناوی خانەکە html ـە

        if not title or not html:
            flash("تایتڵ و ناوەڕۆک (HTML) پێویستن.", "error")
            # فۆڕمەکە دوبارە پیشانبدە بێ بڕۆیەوە
            return render_template("admin_page_new.html", form={"title":title, "slug":slug_in, "html":html})

        slug = slugify(slug_in or title)
        con = db(); c = con.cursor()
        try:
            c.execute("INSERT INTO pages(slug,title,html) VALUES (?,?,?)", (slug, title, html))
            con.commit()
        except sqlite3.IntegrityError as e:
            con.rollback(); con.close()
            flash("ئەم slug ـە پێشتر هەیە.", "error")
            return render_template("admin_page_new.html", form={"title":title, "slug":slug_in, "html":html})
        con.close()
        flash("پەڕە دروست کرا.")
        return redirect(url_for("admin_pages"))

    return render_template("admin_page_new.html", form={"title":"", "slug":"", "html":""})

@app.route("/admin/pages/<slug>/edit", methods=["GET","POST"])
@admin_required
def admin_page_edit(slug):
    con = db(); c = con.cursor()
    p = c.execute("SELECT * FROM pages WHERE slug=?", (slug,)).fetchone()
    if not p:
        con.close(); abort(404)

    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        html  = (request.form.get("html") or "").strip()  # ⭐ هەمان ناو
        if not title or not html:
            con.close()
            flash("تایتڵ و ناوەڕۆک پێویستن.", "error")
            return render_template("admin_page_edit.html", page=p, form={"title":title or p["title"], "html":html})
        c.execute("UPDATE pages SET title=?, html=?, updated_at=CURRENT_TIMESTAMP WHERE slug=?", (title, html, slug))
        con.commit(); con.close()
        flash("پەڕە نوێکرایەوە.")
        return redirect(url_for("admin_pages"))

    form = {"title": p["title"], "html": p["html"]}
    con.close()
    return render_template("admin_page_edit.html", page=p, form=form)
@app.route("/admin/pages/<slug>/delete", methods=["POST"]) 
@admin_required
def admin_page_delete(slug):
    con = db(); c = con.cursor()
    c.execute("DELETE FROM pages WHERE slug=?", (slug,))
    con.commit(); con.close()
    flash("پەڕە سڕایەوە."); return redirect(url_for("admin_pages"))
@app.route("/admin/surveys/<int:survey_id>/edit", methods=["GET","POST"])
@admin_required
def admin_survey_edit(survey_id):
    con = db(); c = con.cursor()
    s = c.execute("SELECT * FROM surveys WHERE id=?", (survey_id,)).fetchone()
    if not s:
        con.close(); abort(404)

    if request.method == "POST":
        title   = (request.form.get("title") or s["title"]).strip()
        desc    = (request.form.get("description") or "").strip()
        try:
            reward  = int(request.form.get("reward_points") or s["reward_points"] or 0)
        except ValueError:
            reward = s["reward_points"] or 0
        allowm  = 1 if request.form.get("allow_multiple") in ("on","1","true") else 0
        is_act  = 1 if request.form.get("is_active") in ("on","1","true") else 0

        c.execute("""UPDATE surveys
                     SET title=?, description=?, reward_points=?, allow_multiple=?, is_active=?
                     WHERE id=?""",
                  (title, desc, reward, allowm, is_act, survey_id))
        con.commit(); con.close()
        flash("ڕاپرسی نوێکرایەوە.")
        return redirect(url_for("admin_surveys"))

    con.close()
    return render_template("admin_survey_edit.html", s=s)


# ------------ Admin: Uploads ------------
@app.route("/admin/uploads", methods=["GET","POST"]) 
@admin_required
def admin_uploads():
    if request.method == "POST":
        files = request.files.getlist("files")
        saved = []
        for f in files:
            if f and allowed_file(f.filename):
                name = secure_filename(f.filename)
                base, ext = os.path.splitext(name)
                unique = f"{slugify(base)}-{secrets.token_hex(4)}{ext}"
                f.save(os.path.join(UPLOAD_FOLDER, unique))
                saved.append(unique)
        flash(f"{len(saved)} فایل بارکرا." if saved else "هیچ فایلێک بارنەکرا.")
        return redirect(url_for("admin_uploads"))
    files = []
    for nm in sorted(os.listdir(UPLOAD_FOLDER), reverse=True)[:300]:
        p = os.path.join(UPLOAD_FOLDER, nm)
        if os.path.isfile(p):
            files.append({
                "name": nm,
                "url": url_for("static", filename=f"uploads/{nm}"),
                "size": os.path.getsize(p)
            })
    return render_template("admin_uploads.html", files=files)

@app.route("/admin/uploads/delete", methods=["POST"]) 
@admin_required
def admin_uploads_delete():
    name = os.path.basename(request.form.get("name",""))
    path = os.path.join(UPLOAD_FOLDER, name)
    if os.path.isfile(path):
        os.remove(path); flash("فایل سڕایەوە.")
    else:
        flash("فایل نەدۆزرایەوە.")
    return redirect(url_for("admin_uploads"))

# ------------ Admin: Profile Options (classic lists) ------------
@app.route("/admin/profile-options", methods=["GET","POST"]) 
@admin_required
def admin_profile_options():
    defaults = {
      "degrees": ["بێ بڕوانامە","سەرەتایی","ناوەندی","ئامادەیی","دبلۆم","بكالۆریۆس","دبلۆمی باڵا","ماستەر","دكتۆرا"],
      "cities": ["هەولێر","سلێمانی","دهۆک","کەرکوک","مووسڵ","بەغداد","بەصرە","نەجەف","کەربەلا"],
      "famstat": ["خێزاندار","سەڵت","جیابووەوە","نەمانی هاوسەر"],
      "work_types": ["حکومی","ئەهلی","سەربەخۆ","رێکخراوەیی","حزبی","هیتر"],
    }
    def get_list_setting_local(key, default_list):
        try:
            raw = get_setting(key)
            if raw:
                arr = json.loads(raw)
                if isinstance(arr, list): return arr
        except Exception: pass
        return default_list

    if request.method == "POST":
        for k in defaults.keys():
            text = (request.form.get(k,"") or "").strip()
            arr = [x.strip() for x in text.split(",") if x.strip()]
            set_setting(f"opt_{k}", json.dumps(arr, ensure_ascii=False))
        flash("هەموو ئۆپشنەکان نوێکرانەوە."); return redirect(url_for("admin_profile_options"))
    data = {k: ", ".join(get_list_setting_local(f"opt_{k}", v)) for k, v in defaults.items()}
    return render_template("admin_profile_options.html", data=data)

# ------------ Admin: Dynamic Profile Schema (Packages/Questions CRUD) ------------
@app.route("/admin/profile/schema") 
@admin_required
def admin_profile_schema():
    con = db(); c = con.cursor()
    packages = c.execute("SELECT * FROM profile_packages ORDER BY position, code").fetchall()
    qs = c.execute("SELECT * FROM profile_questions ORDER BY pkg_code, position, id").fetchall()
    questions_by_pkg = {}
    for q in qs:
        pkg = q["pkg_code"]
        options = []
        if q["options_json"]:
            try: options = json.loads(q["options_json"]) 
            except: options = []
        qd = dict(q); qd["options"]=options
        questions_by_pkg.setdefault(pkg, []).append(qd)
    con.close()
    return render_template("admin_profile_schema.html", packages=packages, questions_by_pkg=questions_by_pkg)

@app.route("/admin/profile/packages/new", methods=["GET","POST"]) 
@admin_required
def admin_profile_pkg_new():
    if request.method == "POST":
        title = request.form.get("title","").strip()
        code  = slugify(request.form.get("code","").strip() or title)
        pos   = int(request.form.get("position") or 0)
        if not title: flash("تايتڵ پێویستە."); return redirect(url_for("admin_profile_pkg_new"))
        con = db(); c = con.cursor()
        try:
            c.execute("INSERT INTO profile_packages(code,title,position) VALUES (?,?,?)", (code,title,pos))
            con.commit()
        except sqlite3.IntegrityError:
            c.rollback(); con.close(); flash("ئەم کۆدە پێشتر هەیە."); return redirect(url_for("admin_profile_pkg_new"))
        con.close(); flash("پاکێج دروست کرا."); return redirect(url_for("admin_profile_schema"))
    return render_template("admin_profile_pkg_form.html", mode="new", pkg=None)

@app.route("/admin/profile/packages/<code>/edit", methods=["GET","POST"]) 
@admin_required
def admin_profile_pkg_edit(code):
    con = db(); c = con.cursor()
    pkg = c.execute("SELECT * FROM profile_packages WHERE code=?", (code,)).fetchone()
    if not pkg: con.close(); abort(404)
    if request.method == "POST":
        title = request.form.get("title","").strip()
        pos   = int(request.form.get("position") or 0)
        c.execute("UPDATE profile_packages SET title=?, position=? WHERE code=?", (title,pos,code))
        con.commit(); con.close(); flash("پاکێج نوێ کرایەوە."); return redirect(url_for("admin_profile_schema"))
    con.close(); return render_template("admin_profile_pkg_form.html", mode="edit", pkg=pkg)

# delete package
@app.route("/admin/profile/packages/<code>/delete", methods=["POST"]) 
@admin_required
def admin_profile_pkg_delete(code):
    con = db(); c = con.cursor()
    c.execute("DELETE FROM profile_packages WHERE code=?", (code,))
    con.commit(); con.close()
    flash("پاکێج سڕایەوە.")
    return redirect(url_for("admin_profile_schema"))

@app.route("/admin/profile/packages/<code>/questions/new", methods=["GET","POST"]) 
@admin_required
def admin_profile_q_new(code):
    con = db(); c = con.cursor()
    pkg = c.execute("SELECT * FROM profile_packages WHERE code=?", (code,)).fetchone()
    if not pkg: con.close(); abort(404)
    if request.method == "POST":
        q_text = request.form.get("q_text","").strip()
        q_type = request.form.get("q_type","text")
        required = 1 if request.form.get("required") in ("1","on","true") else 0
        position = int(request.form.get("position") or 0)
        expose   = 1 if request.form.get("expose_for_rules") in ("1","on","true") else 0
        options  = request.form.get("options","").strip()
        show_if_json = request.form.get("show_if_json", "").strip()
        opts = []
        if q_type in ("select","radio","checkbox"):
            opts = [x.strip() for x in options.split(",") if x.strip()]
        c.execute("""INSERT INTO profile_questions(pkg_code,q_text,q_type,options_json,required,position,expose_for_rules)
                     VALUES (?,?,?,?,?,?,?)""",
                  (code, q_text, q_type, json.dumps(opts, ensure_ascii=False), required, position, expose))
        con.commit(); con.close(); flash("پرسیار زیادکرا."); return redirect(url_for("admin_profile_schema"))
    con.close(); return render_template("admin_profile_q_form.html", mode="new", pkg=pkg, q=None)

@app.route("/admin/profile/packages/<code>/questions/<int:qid>/edit", methods=["GET","POST"]) 
@admin_required
def admin_profile_q_edit(code, qid):
    con = db(); c = con.cursor()
    pkg = c.execute("SELECT * FROM profile_packages WHERE code=?", (code,)).fetchone()
    q   = c.execute("SELECT * FROM profile_questions WHERE id=? AND pkg_code=?", (qid, code)).fetchone()
    if not pkg or not q: con.close(); abort(404)
    if request.method == "POST":
        q_text = request.form.get("q_text","").strip()
        q_type = request.form.get("q_type","text")
        required = 1 if request.form.get("required") in ("1","on","true") else 0
        position = int(request.form.get("position") or 0)
        expose   = 1 if request.form.get("expose_for_rules") in ("1","on","true") else 0
        options  = request.form.get("options","").strip()
        opts = []
        if q_type in ("select","radio","checkbox"):
            opts = [x.strip() for x in options.split(",") if x.strip()]
        c.execute("""UPDATE profile_questions
                     SET q_text=?, q_type=?, options_json=?, required=?, position=?, expose_for_rules=?
                     WHERE id=? AND pkg_code=?""",
                  (q_text, q_type, json.dumps(opts, ensure_ascii=False), required, position, expose, qid, code))
        con.commit(); con.close(); flash("پرسیار نوێ کرایەوە."); return redirect(url_for("admin_profile_schema"))
    qd = dict(q)
    try:
        qd["options"] = json.loads(q["options_json"]) if q["options_json"] else []
    except Exception:
        qd["options"] = []
    con.close(); return render_template("admin_profile_q_form.html", mode="edit", pkg=pkg, q=qd)

@app.route("/admin/profile/packages/<code>/questions/<int:qid>/delete", methods=["POST"]) 
@admin_required
def admin_profile_q_delete(code, qid):
    con = db(); c = con.cursor()
    c.execute("DELETE FROM profile_questions WHERE id=? AND pkg_code=?", (qid, code))
    con.commit(); con.close()
    flash("پرسیار سڕایەوە."); return redirect(url_for("admin_profile_schema"))

# ------------ Admin: Surveys (with eligibility rules) ------------
@app.route("/admin/surveys") 
@admin_required
def admin_surveys():
    con = db(); c = con.cursor()
    rows = c.execute("SELECT * FROM surveys ORDER BY id DESC").fetchall()
    con.close()
    return render_template("admin_surveys.html", rows=rows)

@app.route("/admin/surveys/new", methods=["GET","POST"]) 
@admin_required
def admin_survey_new():
    if request.method=="POST":
        title = request.form.get("title","").strip()
        desc  = request.form.get("description","").strip()
        reward= int(request.form.get("reward_points") or 10)
        allowm= 1 if request.form.get("allow_multiple")=="on" else 0
        if not title: flash("تايتڵ پێویستە."); return redirect(url_for("admin_survey_new"))
        con = db(); c = con.cursor()
        c.execute("""INSERT INTO surveys(title,description,reward_points,allow_multiple,created_by)
                     VALUES (?,?,?,?,?)""", (title,desc,reward,allowm,session["user_id"]))
        con.commit(); con.close(); flash("ڕاپرسی دروست کرا."); return redirect(url_for("admin_surveys"))
    return render_template("admin_survey_new.html")

@app.route("/admin/surveys/<int:survey_id>/toggle", methods=["POST"]) 
@admin_required
def admin_survey_toggle(survey_id):
    con = db(); c = con.cursor()
    c.execute("UPDATE surveys SET is_active = 1 - is_active WHERE id=?", (survey_id,))
    con.commit(); con.close()
    return redirect(url_for("admin_surveys"))

@app.route("/admin/surveys/<int:survey_id>/questions", methods=["GET","POST"]) 
@admin_required
def admin_survey_questions(survey_id):
    con = db(); c = con.cursor()
    s = c.execute("SELECT * FROM surveys WHERE id=?", (survey_id,)).fetchone()
    if not s: con.close(); abort(404)
    if request.method=="POST":
        q_text = request.form.get("q_text","").strip()
        q_type = request.form.get("q_type","text")
        required = 1 if request.form.get("required")=="on" else 0
        options  = request.form.get("options","").strip()
        show_if_json = request.form.get("show_if_json","").strip()
        opts = []
        if q_type in ("select","radio","checkbox"):
            opts = [x.strip() for x in options.split(",") if x.strip()]
        pos = c.execute("SELECT COALESCE(MAX(position),0)+1 FROM survey_questions WHERE survey_id=?", (survey_id,)).fetchone()[0]
        c.execute("""INSERT INTO survey_questions(survey_id,q_text,q_type,options_json,required,position,show_if_json)
                     VALUES (?,?,?,?,?,?,?)""", (survey_id, q_text, q_type, json.dumps(opts, ensure_ascii=False), required, pos, show_if_json))
        con.commit()
    qs = c.execute("SELECT * FROM survey_questions WHERE survey_id=? ORDER BY position,id", (survey_id,)).fetchall()
    con.close()
    return render_template("admin_survey_questions.html", survey=s, questions=qs)

@app.route("/admin/surveys/<int:survey_id>/questions/<int:q_id>/delete", methods=["POST"]) 
@admin_required
def admin_survey_q_delete(survey_id, q_id):
    con = db(); c = con.cursor()
    c.execute("DELETE FROM survey_questions WHERE id=? AND survey_id=?", (q_id, survey_id))
    con.commit(); con.close()
    return redirect(url_for("admin_survey_questions", survey_id=survey_id))

@app.route("/admin/surveys/<int:survey_id>/rules", methods=["GET","POST"]) 
@admin_required
def admin_survey_rules(survey_id):
    con = db(); c = con.cursor()
    s = c.execute("SELECT * FROM surveys WHERE id=?", (survey_id,)).fetchone()
    if not s: con.close(); abort(404)
    row = c.execute("SELECT rules_json FROM survey_eligibility WHERE survey_id=?", (survey_id,)).fetchone()
    rules = json.loads(row["rules_json"]) if row else {}

    # use ALL profile questions (no expose filter)
    fields = []
    pq = c.execute("""SELECT q.*, p.title AS pkg_title FROM profile_questions q
                      JOIN profile_packages p ON p.code=q.pkg_code
                      ORDER BY p.position, q.position, q.id""").fetchall()
    for q in pq:
        f = {"key": f"q_{q['id']}", "label": f"{q['pkg_title']} — {q['q_text']}", "type": q["q_type"]}
        try:
            f["options"] = json.loads(q["options_json"]) if q["options_json"] else []
        except Exception:
            f["options"] = []
        fields.append(f)
    con.close()

    if request.method == "POST":
        def arr(name): return [x.strip() for x in request.form.get(name,"").split(",") if x.strip()]
        data = {
            "min_age": int(request.form.get("min_age")) if request.form.get("min_age") else None,
            "max_age": int(request.form.get("max_age")) if request.form.get("max_age") else None,
            "degrees": arr("degrees"),
            "cities": arr("cities"),
            "family_status": arr("family_status"),
            "work_types": arr("work_types"),
            "gender": request.form.get("gender"),
            "political_member": request.form.get("political_member"),
            "advanced_rules_json": json.loads(request.form.get("advanced_rules_json","[]") or "[]"),
        }
        data = {k:v for k,v in data.items() if v not in (None, "", [])}

        coni = db(); ci = coni.cursor()
        if row:
            ci.execute("UPDATE survey_eligibility SET rules_json=? WHERE survey_id=?", (json.dumps(data, ensure_ascii=False), survey_id))
        else:
            ci.execute("INSERT INTO survey_eligibility(survey_id,rules_json) VALUES (?,?)", (survey_id, json.dumps(data, ensure_ascii=False)))
        coni.commit(); coni.close()
        flash("مەرجەکان پاشەکەوت کران.")
        return redirect(url_for("admin_surveys"))

    return render_template("admin_survey_rules.html", survey=s, rules=rules, rule_fields=fields)

# ------------ Eligibility helpers ------------
def profile_core(user_id):
    con = db(); c = con.cursor()
    p = c.execute("SELECT * FROM profiles WHERE user_id=?", (user_id,)).fetchone()
    con.close()
    return dict(p) if p else {}

def get_answer_map(user_id):
    con = db(); c = con.cursor()
    rows = c.execute("SELECT question_id, answer_text FROM profile_answers WHERE user_id=?", (user_id,)).fetchall()
    con.close()
    return {f"q_{r['question_id']}": (r["answer_text"] or "") for r in rows}

def has_min_profile(user_id):
    # legacy checker (not used for survey eligibility anymore)
    p = profile_core(user_id)
    need = ["age","degree","city","political_member","gender"]
    return all(p.get(k) not in (None, "", 0) for k in need)

def eval_advanced_rules(user_id, adv_rules):
    if not adv_rules: return True
    amap = get_answer_map(user_id)

    def match(rule):
        key = rule.get("key"); op = rule.get("op"); val = rule.get("val")
        ans = amap.get(key, "")
        if op == "=":
            return ans == str(val)
        if op == "in":
            if isinstance(val, list):
                return ans in [str(v) for v in val]
            return ans in [v.strip() for v in str(val).split(",")]
        if op == ">=":
            try: return float(ans) >= float(val)
            except: return False
        if op == "<=":
            try: return float(ans) <= float(val)
            except: return False
        if op == "contains":
            return str(val) in ans
        return True

    return all(match(r) for r in adv_rules)

def eligible(user_id, survey_id):
    con = db(); c = con.cursor()
    row = c.execute("SELECT rules_json FROM survey_eligibility WHERE survey_id=?", (survey_id,)).fetchone()
    con.close()
    if not row:
        return True, None
    rules = json.loads(row["rules_json"] or "{}")
    p  = profile_core(user_id)

    def ck_age():
        if "min_age" in rules and (not p.get("age") or int(p["age"]) < int(rules["min_age"])): return False
        if "max_age" in rules and (not p.get("age") or int(p["age"]) > int(rules["max_age"])): return False
        return True
    def ck_in(key, arr):
        if not arr: return True
        return (p.get(key) in arr)
    def ck_gender():
        g = rules.get("gender")
        if not g or g=="هەردوو": return True
        return p.get("gender")==g
    def ck_pol():
        g = rules.get("political_member")
        if not g or g=="هەردوو": return True
        return p.get("political_member")==g

    simple_ok = (
        ck_age() and
        ck_in("degree", rules.get("degrees", [])) and
        ck_in("city", rules.get("cities", [])) and
        ck_in("family_status", rules.get("family_status", [])) and
        ck_in("work_type", rules.get("work_types", [])) and
        ck_gender() and
        ck_pol()
    )

    adv_ok = eval_advanced_rules(user_id, rules.get("advanced_rules_json"))

    return simple_ok and adv_ok, rules

# ------------ Survey Fill ------------
@app.route("/surveys/<int:survey_id>/fill", methods=["GET","POST"]) 
@login_required
def survey_fill(survey_id):
    # NEW: require ALL profile packages completed
    ok_pkg, missing = completed_all_packages(session["user_id"]) 
    if not ok_pkg:
        flash("تکایە سەرەتا هەموو پاکێجەکانی پڕۆفایل پڕبکەوە.")
        return redirect(url_for("profile"))

    ok, _rules = eligible(session["user_id"], survey_id)
    if not ok:
        flash("ببورە، مەرجەکانت پڕ ناکات بۆ ئەم ڕاپرسییە.")
        return redirect(url_for("surveys_page"))

    con = db(); c = con.cursor()
    s = c.execute("SELECT * FROM surveys WHERE id=? AND is_active=1", (survey_id,)).fetchone()
    if not s: con.close(); abort(404)

    if not s["allow_multiple"]:
        ex = c.execute("SELECT 1 FROM survey_responses WHERE survey_id=? AND user_id=?", (survey_id, session["user_id"])).fetchone()
        if ex:
            con.close(); flash("تۆ پێشتر ئەم ڕاپرسییەت پڕکردووە."); return redirect(url_for("surveys_page"))

    qs_db = c.execute("SELECT * FROM survey_questions WHERE survey_id=? ORDER BY position,id", (survey_id,)).fetchall()
    questions = []
    for q in qs_db:
        opts = []
        if q["options_json"]:
            try: opts = json.loads(q["options_json"]) 
            except: opts = []
        questions.append({**dict(q), "options": opts})

    if request.method == "POST":
        c.execute("INSERT INTO survey_responses(survey_id,user_id) VALUES (?,?)", (survey_id, session["user_id"]))
        rid = c.lastrowid
        for q in questions:
            name = f"q{q['id']}"
            qt = q["q_type"]
            val = ", ".join(request.form.getlist(name)) if qt=="checkbox" else request.form.get(name,"").strip()
            c.execute("INSERT INTO survey_response_items(response_id,question_id,answer_text) VALUES (?,?,?)",
                      (rid, q["id"], val))
        con.commit()
        pts = int(s["reward_points"] or 0)
        con.close()
        if pts:
            add_points(session["user_id"], pts, f"پڕکردنەوەی ڕاپرسی #{s['id']}", "earn")
        return render_template("survey_thanks.html", survey=s, reward_points=pts)

    con.close()
    return render_template("survey_fill.html", survey=s, questions=questions)

# ------------ Admin: Ads / Games ------------
@app.route("/admin/ads", methods=["GET","POST"]) 
@admin_required
def admin_ads():
    con = db(); c = con.cursor()
    if request.method=="POST":
        title = request.form.get("title","").strip()
        image = request.form.get("image_url","").strip()
        link  = request.form.get("link_url","").strip()
        # پۆینتی نوێ زیاد بکە
        reward_points = int(request.form.get("reward_points", get_setting("pts_ad_view","2")))
        c.execute("INSERT INTO ads(title,image_url,link_url,reward_points) VALUES (?,?,?,?)", 
                  (title,image,link,reward_points))
        con.commit()
    rows = c.execute("SELECT * FROM ads ORDER BY id DESC").fetchall()
    con.close()
    return render_template("admin_ads.html", rows=rows)
# فەنکشنی نوێ بۆ دەستکاریکردنی ڕێکلام
@app.route("/admin/ads/<int:ad_id>/edit", methods=["GET","POST"]) 
@admin_required
def admin_ads_edit(ad_id):
    con = db(); c = con.cursor()
    ad = c.execute("SELECT * FROM ads WHERE id=?", (ad_id,)).fetchone()
    if not ad:
        con.close(); abort(404)
    
    if request.method == "POST":
        title = request.form.get("title","").strip()
        image = request.form.get("image_url","").strip()
        link  = request.form.get("link_url","").strip()
        reward_points = int(request.form.get("reward_points", 2))
        
        c.execute("""UPDATE ads 
                     SET title=?, image_url=?, link_url=?, reward_points=? 
                     WHERE id=?""", 
                  (title, image, link, reward_points, ad_id))
        con.commit(); con.close()
        flash("ڕێکلام نوێکرایەوە.")
        return redirect(url_for("admin_ads"))
    
    con.close()
    return render_template("admin_ad_edit.html", ad=ad)

@app.route("/admin/ads/<int:ad_id>/toggle", methods=["POST"]) 
@admin_required
def admin_ad_toggle(ad_id):
    con = db(); c = con.cursor()
    c.execute("UPDATE ads SET is_active = 1 - is_active WHERE id=?", (ad_id,))
    con.commit(); con.close()
    return redirect(url_for("admin_ads"))

@app.route("/admin/ads/<int:ad_id>/delete", methods=["POST"]) 
@admin_required
def admin_ad_delete(ad_id):
    con = db(); c = con.cursor()
    c.execute("DELETE FROM ads WHERE id=?", (ad_id,))
    con.commit(); con.close()
    return redirect(url_for("admin_ads"))

@app.route("/admin/games", methods=["GET","POST"]) 
@admin_required
def admin_games():
    con = db(); c = con.cursor()
    if request.method=="POST":
        title = request.form.get("title","").strip()
        embed = request.form.get("embed_url","").strip()
        c.execute("INSERT INTO games(title,embed_url) VALUES (?,?)", (title,embed))
        con.commit()
    rows = c.execute("SELECT * FROM games ORDER BY id DESC").fetchall()
    con.close()
    return render_template("admin_games.html", rows=rows)

@app.route("/admin/games/<int:game_id>/toggle", methods=["POST"]) 
@admin_required
def admin_game_toggle(game_id):
    con = db(); c = con.cursor()
    c.execute("UPDATE games SET is_active = 1 - is_active WHERE id=?", (game_id,))
    con.commit(); con.close()
    return redirect(url_for("admin_games"))

@app.route("/admin/games/<int:game_id>/delete", methods=["POST"]) 
@admin_required
def admin_game_delete(game_id):
    con = db(); c = con.cursor()
    c.execute("DELETE FROM games WHERE id=?", (game_id,))
    con.commit(); con.close()
    return redirect(url_for("admin_games"))

# ------------ Admin: Payout moderation ------------
@app.route("/admin/payouts", methods=["GET","POST"]) 
@admin_required
def admin_payouts():
    con = db(); c = con.cursor()

    ##__PAYOUTS_FILTERS__
    # ---- Filters from querystring ----
    q_status = (request.args.get('status') or '').strip()       # pending|paid|approved|rejected|''
    q_source = (request.args.get('source') or '').strip()
    q_from   = (request.args.get('from') or '').strip()         # YYYY-MM-DD
    q_to     = (request.args.get('to') or '').strip()           # YYYY-MM-DD

    # Detect columns
    cols = set()
    try:
        cols = {r[1] for r in c.execute("PRAGMA table_info(payout_requests)").fetchall()}
    except Exception:
        pass

    where = []
    params = []

    # Status filter
    if q_status and 'status' in cols:
        where.append("status = ?")
        params.append(q_status)

    # Source filter (LIKE)
    if q_source and 'source' in cols:
        where.append("COALESCE(source,'') LIKE ?")
        params.append('%'+q_source+'%')

    # Date range: choose a sensible date column
    date_col = 'processed_at' if 'processed_at' in cols else ('created_at' if 'created_at' in cols else None)
    if date_col:
        if q_from:
            where.append(f"date({date_col}) >= date(?)")
            params.append(q_from)
        if q_to:
            where.append(f"date({date_col}) <= date(?)")
            params.append(q_to)

    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    if request.method == "POST":
        pid = int(request.form.get("pid"))
        action = request.form.get("action")
        row = c.execute("SELECT * FROM payout_requests WHERE id=?", (pid,)).fetchone()
        if row and row["status"]=="pending":
            if action=="approve":
                c.execute("UPDATE payout_requests SET status='approved', processed_at=CURRENT_TIMESTAMP WHERE id=?", (pid,))
                add_points(row["user_id"], 0, f"پارەدان تایید کرا ({row['points']} pts → {row['money_cents']} IQD)", "payout")
            elif action=="reject":
                add_points(row["user_id"], row["points"], "ڕەدکردنی پارەدان (گەڕاندنەوەی پۆینت)", "adjust")
                c.execute("UPDATE payout_requests SET status='rejected', processed_at=CURRENT_TIMESTAMP WHERE id=?", (pid,))
            con.commit()
    rows = c.execute("SELECT pr.*, u.username FROM payout_requests pr LEFT JOIN users u ON u.id=pr.user_id ORDER BY id DESC").fetchall()
    con.close()
    return render_template("admin_payouts.html", rows=rows)

# ------------ Admin: Wallet Adjust (ADMIN ONLY manual points) ------------
@app.route("/admin/wallet/adjust", methods=["GET","POST"]) 
@admin_required
def admin_wallet_adjust():
    if request.method == "POST":
        ident = (request.form.get("ident","") or "").strip().lower()  # username یان email
        pts   = int(request.form.get("points") or 0)
        note  = (request.form.get("note","") or "").strip() or "manual adjust"
        con = db(); c = con.cursor()
        u = c.execute("SELECT id,username,email FROM users WHERE lower(username)=? OR lower(email)=?",
                      (ident, ident)).fetchone()
        if not u:
            con.close(); flash("بەکارهێنەر نەدۆزرایەوە."); return redirect(url_for("admin_wallet_adjust"))
        uid = u["id"]
        con.close()
        add_points(uid, pts, note, "adjust")
        flash(f"پۆینت {pts:+} بۆ @{u['username']} زیاد/کەم کرا.")
        return redirect(url_for("admin_wallet_adjust"))

    # recent transactions
    con = db(); c = con.cursor()
    tx = c.execute("""
      SELECT wt.*, u.username FROM wallet_transactions wt
      LEFT JOIN users u ON u.id = wt.user_id
      ORDER BY wt.id DESC LIMIT 50
    """).fetchall()
    con.close()
    return render_template("admin_wallet_adjust.html", tx=tx)

# ------------ Admin: Settings (set 1 point = X IQD, etc.) ------------
@app.route("/admin/settings", methods=["GET","POST"]) 
@admin_required
def admin_settings():
    keys = ["money_per_point","min_payout_points","pts_profile_section","pts_ad_view","pts_game_play"]
    if request.method == "POST":
        for k in keys:
            v = (request.form.get(k,"") or "").strip()
            if v != "":
                set_setting(k, v)
        flash("ڕێکخستنەکان پاشەکەوت کران.")
        return redirect(url_for("admin_settings"))

    data = {k:int(get_setting(k,"0")) for k in keys}
    return render_template("admin_settings.html", data=data)

# ------------ Error ------------
@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404
# === FIX: ensure /admin/games/<id>/edit exists ===
if 'admin_games_edit' not in app.view_functions:
    @app.route("/admin/games/<int:game_id>/edit", methods=["GET","POST"], endpoint='admin_games_edit')
    @admin_required
    def admin_games_edit(game_id):
        con = db(); c = con.cursor()
        g = c.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
        if not g:
            con.close()
            abort(404)

        if request.method == "POST":
            title = (request.form.get("title") or "").strip()
            play_url = (request.form.get("play_url") or "").strip()
            embed_html = request.form.get("embed_html") or ""
            thumbnail = (request.form.get("thumbnail_url") or "").strip()
            pts = request.form.get("points_override")
            secs = request.form.get("min_seconds_override")
            points_override = None if pts in (None, "", "None") else max(0, int(pts))
            min_seconds_override = None if secs in (None, "", "None") else max(0, int(secs))

            if not title:
                con.close()
                flash("تايتڵ پێویستە.")
                return redirect(url_for("admin_games_edit", game_id=game_id))

            c.execute("""
                UPDATE games SET title=?, play_url=?, embed_html=?, thumbnail_url=?,
                                 points_override=?, min_seconds_override=?
                WHERE id=?""",
                (title, play_url, embed_html, thumbnail, points_override, min_seconds_override, game_id))
            con.commit()
            con.close()
            flash("پاشەکەوت کرا.")
            return redirect(url_for("admin_games_edit", game_id=game_id))

        default_pts  = int(get_setting("games_points_per_play", "5") or 5)
        default_secs = int(get_setting("games_min_seconds", "30") or 30)
        maps = c.execute("""
            SELECT ga.position, a.id AS ad_id, a.title AS ad_title FROM game_ads ga JOIN ads a ON a.id = ga.ad_id
            WHERE ga.game_id = ?""", (game_id,)).fetchall()
        all_ads = c.execute("SELECT id, title FROM ads ORDER BY id DESC").fetchall()
        con.close()

        try:
            return render_template("admin_games_edit.html",
                                   g=g, default_pts=default_pts, default_secs=default_secs,
                                   maps=maps, all_ads=all_ads)
        except Exception:
            return f"<!doctype html><meta charset='utf-8'><h3>Edit Game #{g['id']}</h3>"
# ===== Debug helpers (safe to add multiple times) =====
def ensure_debug_routes(app):
    if "_routes" not in app.view_functions:
        @app.route("/_routes")
        def _routes():
            rows = []
            for r in app.url_map.iter_rules():
                methods = ",".join(sorted(m for m in r.methods if m in
                                          ("GET","POST","PUT","PATCH","DELETE","OPTIONS")))
                rows.append(f"{r.rule:40} → endpoint={r.endpoint}  [{methods}]")
            return "<pre>" + "\n".join(sorted(rows)) + "</pre>"

    if "healthz" not in app.view_functions:
        @app.route("/healthz")
        def healthz():
            return "ok", 200
# --- Alias/fallback for admin_pages_list ---
if "admin_pages_list" not in app.view_functions:
    @app.route("/admin/pages", endpoint="admin_pages_list")
    def _admin_pages_list_alias():
        # ئەگەر api_pages_list هەبوو، هەمانە بانگ بکە
        if "api_pages_list" in app.view_functions:
            return app.view_functions["api_pages_list"]()

        # fallback: هەوڵی لیستکردنی pages لە DB بکە
        rows = []
        try:
            with db() as con:
                rows = con.execute(
                    "SELECT id, slug, title, updated_at FROM pages ORDER BY updated_at DESC, id DESC"
                ).fetchall()
        except Exception:
            pass

        from flask import render_template_string
        items = "".join(
            f"<tr><td>{r['id']}</td>"
            f"<td><a href='/p/{r['slug']}' target='_blank'>{r['slug']}</a></td>"
            f"<td>{r['title']}</td>"
            f"<td>{r['updated_at']}</td></tr>"
            for r in rows
        ) or "<tr><td colspan='4'>هیچ پەڕەیەک نییە.</td></tr>"

        return render_template_string(f"""
<!doctype html><meta charset="utf-8">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
<div class="container py-4" style="max-width:1000px">
  <div class="d-flex justify-content-between align-items-center">
    <h4 class="mb-0">Design — پەڕەکان</h4>
    <div><a class="btn btn-sm btn-primary" href="{{{{ url_for('admin_page_new') if 'admin_page_new' in current_app.view_functions else '#' }}}}">+ پەڕەی نوێ</a></div>
  </div>
  <hr>
  <div class="table-responsive">
    <table class="table table-sm align-middle">
      <thead><tr><th>ID</th><th>Slug</th><th>Title</th><th>Updated</th></tr></thead>
      <tbody>{items}</tbody>
    </table>
  </div>
</div>
""")

# call it once after routes are defined
ensure_debug_routes(app)
# ===== end debug helpers =====
# ==== FIX: toggle endpoint for games (admin_games_toggle vs admin_game_toggle) ====
from flask import current_app

# ڕووتی بنچینەی toggle ئەگەر نییە، دروستی بکە
if 'admin_game_toggle' not in app.view_functions:
    @app.route("/admin/games/<int:game_id>/toggle", methods=["POST"])
    @admin_required
    def admin_game_toggle(game_id):
        con = db(); c = con.cursor()
        g = c.execute("SELECT is_active FROM games WHERE id=?", (game_id,)).fetchone()
        if not g:
            con.close()
            abort(404)
        new_state = 0 if g["is_active"] else 1
        c.execute("UPDATE games SET is_active=? WHERE id=?", (new_state, game_id))
        con.commit(); con.close()
        flash("دۆخی یاری گۆڕدرا.")
        return redirect(url_for("admin_games"))

# ئەلیاس: ئەگەر قالیب بانگ بکات admin_games_toggle، ئەمەش کار دەکات بێ گۆڕینی قالیب
if 'admin_games_toggle' not in app.view_functions:
    @app.route("/__alias/admin/games/<int:game_id>/toggle", endpoint="admin_games_toggle", methods=["POST"])
    @admin_required
    def __alias_admin_games_toggle(game_id):
        return current_app.view_functions['admin_game_toggle'](game_id)
# ==== /FIX ====
# ==== FIX: admin_game_toggle / admin_games_toggle ====
from flask import current_app

# ڕووتی بنچینەی toggle (POST) — ئەگەر نییە دروستی بکە
if 'admin_game_toggle' not in app.view_functions:
    @app.route("/admin/games/<int:game_id>/toggle", methods=["POST"])
    @admin_required
    def admin_game_toggle(game_id):
        con = db(); c = con.cursor()
        row = c.execute("SELECT is_active FROM games WHERE id=?", (game_id,)).fetchone()
        if not row:
            con.close(); abort(404)
        new_state = 0 if row["is_active"] else 1
        c.execute("UPDATE games SET is_active=? WHERE id=?", (new_state, game_id))
        con.commit(); con.close()
        flash("دۆخی یاری گۆڕدرا.")
        return redirect(url_for("admin_games"))

# alias بۆ قالیبەکانی کۆن کە بانگ دەکەن admin_games_toggle
if 'admin_games_toggle' not in app.view_functions:
    @app.route("/__alias/admin/games/<int:game_id>/toggle", endpoint="admin_games_toggle", methods=["POST"])
    @admin_required
    def __alias_admin_games_toggle(game_id):
        return current_app.view_functions['admin_game_toggle'](game_id)

# ==== FIX: admin_game_delete / admin_games_delete ====

# ڕووتی بنچینەی سڕینەوە (POST) — دەباتە admin_games لیستەکەوە
if 'admin_game_delete' not in app.view_functions:
    @app.route("/admin/games/<int:game_id>/delete", methods=["POST"])
    @admin_required
    def admin_game_delete(game_id):
        con = db(); c = con.cursor()
        # پاککردنەوەی هاوپێچەکان بۆ ئەو یاریە
        try:
            c.execute("DELETE FROM game_ads   WHERE game_id=?", (game_id,))
        except Exception:
            pass
        try:
            c.execute("DELETE FROM game_plays WHERE game_id=?", (game_id,))
        except Exception:
            pass
        # خودی یاری
        c.execute("DELETE FROM games WHERE id=?", (game_id,))
        con.commit(); con.close()
        flash("یاری بسڕایەوە.")
        return redirect(url_for("admin_games"))

# alias بۆ ناوی کۆن: admin_games_delete
if 'admin_games_delete' not in app.view_functions:
    @app.route("/__alias/admin/games/<int:game_id>/delete", endpoint="admin_games_delete", methods=["POST"])
    @admin_required
    def __alias_admin_games_delete(game_id):
        return current_app.view_functions['admin_game_delete'](game_id)
# ===== RESCUE PATCH: ensure routes exist & add debug helpers =====
import os, sqlite3
_DB_PATH = os.environ.get("SURVEY_DB", "survey.db")
def get_db():
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    return con
db = get_db

import os, sqlite3
from datetime import date, datetime, timezone
from functools import wraps
from flask import (current_app, render_template, request, redirect, url_for,
                   flash, session, abort)

# 1) Debug helpers: /_routes + /healthz (تەنیا ئەگەر بوونیان نییە)
def _ensure_debug_routes(app):
    if "_routes" not in app.view_functions:
        @app.route("/_routes")
        def _routes():
            rows = []
            for r in app.url_map.iter_rules():
                methods = ",".join(sorted(m for m in r.methods if m in
                                          ("GET","POST","PUT","PATCH","DELETE","OPTIONS")))
                rows.append(f"{r.rule:40} → endpoint={r.endpoint}  [{methods}]")
            return "<pre>" + "\n".join(sorted(rows)) + "</pre>"
    if "healthz" not in app.view_functions:
        @app.route("/healthz")
        def healthz(): return "ok", 200
_ensure_debug_routes(app)

# 2) Dev sessions (local): /dev/admin , /dev/user (ئەگەر نییە)
if "dev_admin" not in app.view_functions:
    @app.route("/dev/admin")
    def dev_admin():
        session["user_id"] = 1
        session["is_admin"] = True
        flash("Dev admin session set.")
        return redirect(url_for("home") if "home" in app.view_functions else "/")

if "dev_user" not in app.view_functions:
    @app.route("/dev/user")
    def dev_user():
        session["user_id"] = 2
        session["is_admin"] = False
        flash("Dev user session set.")
        return redirect(url_for("home") if "home" in app.view_functions else "/")

# 3) Fallback home ئەگەر نەبوو
if "home" not in app.view_functions:
    @app.route("/")
    def home():
        return """<!doctype html><meta charset='utf-8'>
        <div style="font-family:system-ui;max-width:860px;margin:48px auto">
          <h2>SurveyApp</h2>
          <p>Server is running.</p>
          <ul>
            <li><a href="/dev/admin">/dev/admin</a> (set admin)</li>
            <li><a href="/dev/user">/dev/user</a> (set user)</li>
            <li><a href="/_routes">/_routes</a></li>
            <li><a href="/earn/ads">/earn/ads</a></li>
            <li><a href="/earn/games">/earn/games</a></li>
            <li><a href="/admin/ads-earn-settings">/admin/ads-earn-settings</a></li>
          </ul>
        </div>"""

# 4) Helpersی خاڵی (تەنیا بۆ فۆڵبەک): DB + settings (ناویان یەکتازەیە بۆ ناکۆکی)
BASE_DIR = os.path.dirname(__file__)
_DB_PATH = os.path.join(BASE_DIR, "survey.db")
def _db():
    con = sqlite3.connect(_DB_PATH); con.row_factory = sqlite3.Row
    return con

def _ensure_settings_table():
    con = _db(); c = con.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS app_settings(key TEXT PRIMARY KEY, value TEXT)")
    con.commit(); con.close()
_ensure_settings_table()

def _get_setting(k, d=None):
    con = _db(); c = con.cursor()
    r = c.execute("SELECT value FROM app_settings WHERE key=?", (k,)).fetchone()
    con.close()
    return (r["value"] if r else d)

def _set_setting(k, v):
    con = _db(); c = con.cursor()
    if c.execute("SELECT 1 FROM app_settings WHERE key=?", (k,)).fetchone():
        c.execute("UPDATE app_settings SET value=? WHERE key=?", (str(v), k))
    else:
        c.execute("INSERT INTO app_settings(key,value) VALUES (?,?)", (k, str(v)))
    con.commit(); con.close()

# 5) Decoratorsی فۆڵبەک (ئەگەر لەسەرەوە پێناسە نەکراون)
def _login_required(fn):
    @wraps(fn)
    def w(*a, **kw):
        if not session.get("user_id"):
            flash("تکایە بچۆ ژوورەوە.")
            return redirect(url_for("home") if "home" in app.view_functions else "/")
        return fn(*a, **kw)
    return w

def _admin_required(fn):
    @wraps(fn)
    def w(*a, **kw):
        if not session.get("user_id"):
            flash("تکایە بچۆ ژوورەوە.")
            return redirect(url_for("home") if "home" in app.view_functions else "/")
        if not session.get("is_admin"):
            abort(403)
        return fn(*a, **kw)
    return w

# 6) /earn/ads  — تەنیا ئەگەر نییە دروست بکە
if "earn_ads_list" not in app.view_functions:
    # مایگریشنەکانی پێویست بۆ Ads
    con = _db(); c = con.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS ads(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        image_url TEXT,
        link_url TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        points_override INTEGER,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS ad_views(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        ad_id INTEGER NOT NULL,
        viewed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        view_date TEXT NOT NULL,
        UNIQUE(user_id, ad_id, view_date)
    )""")
    # بەهای بنەڕەتی
    if _get_setting("ads_daily_quota") is None: _set_setting("ads_daily_quota","10")
    if _get_setting("ads_points_per_view") is None: _set_setting("ads_points_per_view","2")
    if _get_setting("ads_view_min_seconds") is None: _set_setting("ads_view_min_seconds","10")
    con.commit(); con.close()

    @app.route("/earn/ads")
    @_login_required
    def earn_ads_list():
        try:
            return render_template("earn_ads.html")
        except Exception:
            # فۆڵبەک HTML
            dq = int(_get_setting("ads_daily_quota","10") or 10)
            pp = int(_get_setting("ads_points_per_view","2") or 2)
            ms = int(_get_setting("ads_view_min_seconds","10") or 10)
            return f"""<!doctype html><meta charset='utf-8'>
            <h3 style="font-family:system-ui">Earn Ads</h3>
            <p>Daily quota: {dq} — Points per view: {pp} — Min seconds: {ms}</p>
            <p>هیچ قالبی تایبەت نییە؛ ئەم فۆڵبەکە کار دەکات.</p>"""

# 7) /earn/games  — تەنیا ئەگەر نییە دروست بکە
if "earn_games_list" not in app.view_functions:
    con = _db(); c = con.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS games(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        play_url TEXT,
        embed_html TEXT,
        thumbnail_url TEXT,
        is_active INTEGER NOT NULL DEFAULT 1,
        points_override INTEGER,
        min_seconds_override INTEGER,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS game_plays(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        game_id INTEGER NOT NULL,
        played_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        play_date TEXT NOT NULL,
        UNIQUE(user_id, game_id, play_date)
    )""")
    if _get_setting("games_daily_quota") is None: _set_setting("games_daily_quota","10")
    if _get_setting("games_points_per_play") is None: _set_setting("games_points_per_play","5")
    if _get_setting("games_min_seconds") is None: _set_setting("games_min_seconds","30")
    con.commit(); con.close()

    @app.route("/earn/games")
    @_login_required
    def earn_games_list():
        try:
            return render_template("earn_games.html")
        except Exception:
            dq = int(_get_setting("games_daily_quota","10") or 10)
            pp = int(_get_setting("games_points_per_play","5") or 5)
            ms = int(_get_setting("games_min_seconds","30") or 30)
            return f"""<!doctype html><meta charset='utf-8'>
            <h3 style="font-family:system-ui">Earn Games</h3>
            <p>Daily quota: {dq} — Points per play: {pp} — Min seconds: {ms}</p>
            <p>هیچ قالبی تایبەت نییە؛ فۆڵبەک پیشانی دەدرێت.</p>"""

# 8) /admin/ads-earn-settings — تەنیا ئەگەر نییە دروست بکە
if "admin_ads_earn_settings" not in app.view_functions:
    @app.route("/admin/ads-earn-settings", methods=["GET","POST"])
    @_admin_required
    def admin_ads_earn_settings():
        if request.method == "POST":
            try:
                _set_setting("ads_daily_quota", max(0, int(request.form.get("ads_daily_quota") or "10")))
                _set_setting("ads_points_per_view", max(0, int(request.form.get("ads_points_per_view") or "2")))
                _set_setting("ads_view_min_seconds", max(0, int(request.form.get("ads_view_min_seconds") or "10")))
                flash("پاشەکەوت کرا.")
            except ValueError:
                flash("تکایە ژمارەی دروست بنووسە.")
            return redirect(url_for("admin_ads_earn_settings"))
        data = {
            "ads_daily_quota": _get_setting("ads_daily_quota","10"),
            "ads_points_per_view": _get_setting("ads_points_per_view","2"),
            "ads_view_min_seconds": _get_setting("ads_view_min_seconds","10"),
        }
        try:
            return render_template("admin_ads_earn_settings.html", data=data)
        except Exception:
            return f"""<!doctype html><meta charset='utf-8'>
            <h3 style="font-family:system-ui">Ads Settings</h3>
            <form method="post">
              <div>کۆتایی ڕۆژانە: <input type="number" name="ads_daily_quota" value="{data['ads_daily_quota']}"></div>
              <div>پۆینت/سەیرکردن: <input type="number" name="ads_points_per_view" value="{data['ads_points_per_view']}"></div>
              <div>کەمترین چرکەی سەیرکردن: <input type="number" name="ads_view_min_seconds" value="{data['ads_view_min_seconds']}"></div>
              <button>Save</button>
            </form>"""

print(f"[BOOT] Using file: {__file__}")
print(f"[BOOT] DB path: {_DB_PATH}")
# ===== END RESCUE PATCH =====
# Seed a demo game quickly (dev only)
@app.route("/dev/seed-game")
def dev_seed_game():
    con = db(); c = con.cursor()
    c.execute("INSERT INTO games(title, is_active, embed_html, points_override, min_seconds_override) VALUES (?,?,?,?,?)",
              ("Demo Game", 1, "", 5, 20))
    con.commit(); con.close()
    return "OK: demo game inserted"

# ===================== SAFETY PATCH (auto-generated) =====================
# This block prevents mis-routing of /admin/payouts and defines/aliases
# a few endpoints that frequently caused BuildError in templates.
from flask import request

def __ensure_endpoint(name, rule, view_func, methods=("GET",), endpoint=None):
    """Register a route only if the endpoint is not already present."""
    ep = endpoint or name
    try:
        if ep not in app.view_functions:
            app.add_url_rule(rule, endpoint=ep, view_func=view_func, methods=list(methods))
    except Exception:
        # Avoid hard-crashing in case the map has duplicates; best-effort only.
        pass

# --- Payouts view (minimal), used if your template exists ---
def __admin_payouts_view():
    try:
        # Try to render your real template; parameters are optional
        return render_template("admin_payouts.html")
    except Exception:
        # Fallback minimal HTML so the page always opens
        return "<!doctype html><meta charset='utf-8'><h2 style='font-family:sans-serif'>Payouts</h2><p>Template <code>templates/admin_payouts.html</code> not found.</p>"

# Guarantee the canonical /admin/payouts endpoint
__ensure_endpoint("admin_payouts", "/admin/payouts", __admin_payouts_view, methods=("GET","POST"))

# Guard: if anything tries to redirect /admin/payouts elsewhere, intercept it
@app.before_request
def __force_payouts_page():
    try:
        if request.path.rstrip("/") == "/admin/payouts":
            # Always serve the payouts view directly
            return app.view_functions.get("admin_payouts", __admin_payouts_view)()
    except Exception:
        # Never break the request flow
        return None

# Convenience short alias
__ensure_endpoint("admin_payout", "/admin/payout", lambda: redirect(url_for("admin_payouts")), methods=("GET",))

# --- Admin games: provide both toggle endpoints to avoid BuildError ---
def __toggle_game(game_id: int):
    con = db(); c = con.cursor()
    row = c.execute("SELECT is_active FROM games WHERE id=?", (game_id,)).fetchone()
    if not row:
        con.close(); abort(404)
    newv = 0 if int(row["is_active"] or 0) else 1
    c.execute("UPDATE games SET is_active=? WHERE id=?", (newv, game_id))
    con.commit(); con.close()
    flash("حاڵەتی یاری نوێکرایەوە.")
    return redirect(url_for("admin_games"))

def __admin_games_list():
    con = db(); c = con.cursor()
    rows = c.execute("SELECT * FROM games ORDER BY id DESC").fetchall()
    con.close()
    try:
        return render_template("admin_games.html", rows=rows)
    except Exception:
        # Minimal fallback
        body = ["<h3 style='font-family:sans-serif'>Games</h3><ul>"]
        for r in rows:
            body.append(f"<li>#{r['id']} — {r['title']} — active={r['is_active']}</li>")
        body.append("</ul>")
        return "<!doctype html><meta charset='utf-8'>" + "".join(body)

__ensure_endpoint("admin_games", "/admin/games", __admin_games_list, methods=("GET",))
__ensure_endpoint("admin_game_toggle", "/admin/games/<int:game_id>/toggle", lambda game_id: __toggle_game(game_id), methods=("POST","GET"))
__ensure_endpoint("admin_games_toggle", "/admin/games/<int:game_id>/toggle2", lambda game_id: __toggle_game(game_id), methods=("POST","GET"))

# --- Surveys: safe delete & question actions (to stop BuildError) ---
def __admin_surveys_list():
    con = db(); c = con.cursor()
    rows = c.execute("SELECT * FROM surveys ORDER BY id DESC").fetchall()
    con.close()
    try:
        return render_template("admin_surveys.html", rows=rows)
    except Exception:
        items = "".join([f"<li>#{r['id']} — {r['title']}</li>" for r in rows])
        return f"<!doctype html><meta charset='utf-8'><h3>Surveys</h3><ul>{items}</ul>"

__ensure_endpoint("admin_surveys", "/admin/surveys", __admin_surveys_list, methods=("GET",))

def __delete_survey(survey_id: int):
    con = db(); c = con.cursor()
    # Cascade delete answers and questions via FK if set; otherwise manual
    try:
        c.execute("DELETE FROM surveys WHERE id=?", (survey_id,))
        con.commit()
    finally:
        con.close()
    flash("ڕاپرسی سڕایەوە.")
    return redirect(url_for("admin_surveys"))

__ensure_endpoint("admin_survey_delete",
                  "/admin/surveys/<int:survey_id>/delete",
                  lambda survey_id: __delete_survey(survey_id),
                  methods=("POST","GET"))

# Question edit/move stubs to avoid template 404/BuildError
def __admin_survey_q_move(survey_id: int, q_id: int, direction: str):
    con = db(); c = con.cursor()
    q = c.execute("SELECT id,position FROM survey_questions WHERE id=? AND survey_id=?", (q_id, survey_id)).fetchone()
    if not q:
        con.close(); abort(404)
    pos = int(q["position"] or 0)
    new_pos = pos - 1 if direction == "up" else pos + 1
    # swap with neighbor
    neighbor = c.execute("SELECT id,position FROM survey_questions WHERE survey_id=? AND position=?",
                         (survey_id, new_pos)).fetchone()
    if neighbor:
        c.execute("UPDATE survey_questions SET position=? WHERE id=?", (pos, neighbor["id"]))
    c.execute("UPDATE survey_questions SET position=? WHERE id=?", (new_pos, q_id))
    con.commit(); con.close()
    return redirect(url_for("admin_survey_questions", survey_id=survey_id))

def __admin_survey_q_edit(survey_id: int, q_id: int):
    con = db(); c = con.cursor()
    q = c.execute("SELECT * FROM survey_questions WHERE id=? AND survey_id=?", (q_id, survey_id)).fetchone()
    if request.method == "POST":
        q_text = (request.form.get("q_text") or "").strip()
        q_type = (request.form.get("q_type") or "").strip()
        req    = 1 if request.form.get("required") else 0
        options= (request.form.get("options") or "").strip()
        show_if= (request.form.get("show_if_json") or "").strip()
        c.execute("""UPDATE survey_questions SET q_text=?, q_type=?, required=?,
                     options_json=?, show_if_json=? WHERE id=? AND survey_id=?""",
                  (q_text, q_type, req, options or None, show_if or None, q_id, survey_id))
        con.commit(); con.close()
        flash("پرسیار نوێکرایەوە.")
        return redirect(url_for("admin_survey_questions", survey_id=survey_id))
    con.close()
    # Minimal edit form
    return f"""<!doctype html><meta charset='utf-8'>
    <h3 style='font-family:sans-serif'>دەستکاری پرسیار #{q_id}</h3>
    <form method="post" style="max-width:720px">
      <label>دەقی پرسیار</label><input name="q_text" value="{(q['q_text'] if q else '')}"><br>
      <label>جۆر</label><input name="q_type" value="{(q['q_type'] if q else '')}"><br>
      <label>لازمە؟</label><input type="checkbox" name="required" {"checked" if q and q['required'] else ""}><br>
      <label>ئۆپشنەکان</label><textarea name="options">{(q['options_json'] or '') if q else ''}</textarea><br>
      <label>Show If (JSON)</label><textarea name="show_if_json">{(q['show_if_json'] or '') if q else ''}</textarea><br>
      <button>پاشەکەوت</button>
    </form>"""

__ensure_endpoint("admin_survey_q_move",
                  "/admin/surveys/<int:survey_id>/questions/<int:q_id>/move/<string:direction>",
                  lambda survey_id, q_id, direction: __admin_survey_q_move(survey_id, q_id, direction),
                  methods=("POST","GET"))

__ensure_endpoint("admin_survey_q_edit",
                  "/admin/surveys/<int:survey_id>/questions/<int:q_id>/edit",
                  lambda survey_id, q_id: __admin_survey_q_edit(survey_id, q_id),
                  methods=("GET","POST"))

__ensure_endpoint("admin_survey_q_delete",
                  "/admin/surveys/<int:survey_id>/questions/<int:q_id>/delete",
                  lambda survey_id, q_id: __delete_survey(survey_id),  # fallback; replace with real q-delete if you have one
                  methods=("POST","GET"))

# --- Aliases used in base.html menu to prevent BuildError ---
def __admin_dashboard():
    try:
        return render_template("admin_dashboard.html")
    except Exception:
        return "<!doctype html><meta charset='utf-8'><h3 style='font-family:sans-serif'>Dashboard</h3>"

def __admin_pages():
    # If you have a fancy editor template, it will render. Otherwise fallback.
    try:
        return render_template("admin_pages.html")
    except Exception:
        return "<!doctype html><meta charset='utf-8'><h3 style='font-family:sans-serif'>Pages</h3>"

def __admin_profile_options():
    try:
        return render_template("admin_profile_options.html")
    except Exception:
        return "<!doctype html><meta charset='utf-8'><h3 style='font-family:sans-serif'>Profile Options</h3>"

__ensure_endpoint("admin_dashboard", "/admin", __admin_dashboard, methods=("GET",))
__ensure_endpoint("admin_pages", "/admin/pages", __admin_pages, methods=("GET","POST"))
__ensure_endpoint("admin_profile_options", "/admin/profile/options", __admin_profile_options, methods=("GET","POST"))
# ===================== /SAFETY PATCH =====================
# ===== [PAGES VIEWER FIX] define public page_view by slug =====
from flask import abort, render_template, redirect, url_for

# /p/<slug>  → endpoint=page_view   (ئەمەی url_for('page_view', slug=...) بەکاردێن)
if "page_view" not in app.view_functions:
    def page_view(slug: str):
        con = db(); c = con.cursor()
        row = c.execute("SELECT * FROM pages WHERE slug=?", (slug,)).fetchone()
        con.close()
        if not row:
            abort(404)

        # title & content coalesce
        def _get(d, k, default=""):
            try:
                return d[k] if (hasattr(d, "keys") and k in d.keys()) else default
            except Exception:
                return default

        title = _get(row, "title", _get(row, "slug", slug))
        content_html = _get(row, "content_html", _get(row, "content", ""))

        # Try template; fallback HTML اگر template نیە
        try:
            return render_template("page_view.html", page=row, content_html=content_html)
        except Exception:
            return (
                "<!doctype html><meta charset='utf-8'>"
                f"<h2 style='font-family:sans-serif'>{title}</h2>"
                f"<div>{content_html}</div>"
            )

    app.add_url_rule("/p/<string:slug>", endpoint="page_view", view_func=page_view, methods=["GET"])

# alias: /pages/<slug> → /p/<slug>
if "page_view_alias" not in app.view_functions:
    app.add_url_rule(
        "/pages/<string:slug>",
        endpoint="page_view_alias",
        view_func=lambda slug: redirect(url_for("page_view", slug=slug)),
        methods=["GET"],
    )
# ===== [/PAGES VIEWER FIX] =====


# ==== BEGIN AUTO-PATCH (Games Admin) ====
# Make slashes flexible
try:
    app.url_map.strict_slashes = False
except Exception:
    pass

# Common imports (safe if duplicates)
try:
    from functools import wraps
    from jinja2 import TemplateNotFound as _JinjaTemplateNotFound
except Exception:
    class _JinjaTemplateNotFound(Exception): pass

def _games_inline_new_form():
    return (
        "<!doctype html><meta charset='utf-8'><title>+ یاریی نوێ</title>"
        "<h2 style='font-family:Tahoma,Arial'>+ یاریی نوێ</h2>"
        "<form method='post' action='/admin/games' style='max-width:700px;padding:12px;border:1px solid #ddd;border-radius:10px'>"
        "<label>ناونیشان<br><input name='title' required style='width:100%'></label>"
        "<div style='margin-top:10px'><button>پاشەکەوت</button> <a href='/admin/games'>گەڕانەوە</a></div>"
        "</form>"
    )

def _games_fetch(game_id):
    # Return dict even if DB/row missing
    try:
        con = db(); c = con.cursor()
        row = c.execute("SELECT id,title,thumbnail_url,play_url,embed_html,points_override,min_seconds_override,is_active FROM games WHERE id=?", (game_id,)).fetchone()
        con.close()
        if not row:
            return dict(id=game_id, title="", thumbnail_url="", play_url="", embed_html="", points_override=0, min_seconds_override=0, is_active=1)
        try:
            return dict(row)
        except Exception:
            cols = ["id","title","thumbnail_url","play_url","embed_html","points_override","min_seconds_override","is_active"]
            return {k: row[i] if i < len(row) else None for i,k in enumerate(cols)}
    except Exception:
        return dict(id=game_id, title="", thumbnail_url="", play_url="", embed_html="", points_override=0, min_seconds_override=0, is_active=1)

def _to_int(v, default=0):
    try: return int(v)
    except Exception: return default

def _games_save(game_id, form):
    title = (form.get("title") or "").strip()
    thumbnail_url = (form.get("thumbnail_url") or "").strip()
    play_url = (form.get("play_url") or "").strip()
    embed_html = (form.get("embed_html") or "").strip()
    points_override = _to_int(form.get("points_override") or 0)
    min_seconds_override = _to_int(form.get("min_seconds_override") or 0)
    is_active = 1 if (form.get("is_active") in ("1","on","true","True")) else 0
    try:
        con = db(); c = con.cursor()
        exists = c.execute("SELECT 1 FROM games WHERE id=?", (game_id,)).fetchone()
        if exists:
            c.execute("""
                UPDATE games
                   SET title=?,
                       thumbnail_url=?,
                       play_url=?,
                       embed_html=?,
                       points_override=?,
                       min_seconds_override=?,
                       is_active=?
                 WHERE id=?
            """, (title, thumbnail_url, play_url, embed_html, points_override, min_seconds_override, is_active, game_id))
        else:
            c.execute("""
                INSERT INTO games (id,title,thumbnail_url,play_url,embed_html,points_override,min_seconds_override,is_active)
                VALUES (?,?,?,?,?,?,?,?)
            """, (game_id, title, thumbnail_url, play_url, embed_html, points_override, min_seconds_override, is_active))
        con.commit(); con.close()
        return True
    except Exception:
        try: con.rollback(); con.close()
        except Exception: pass
        return False

# Guarantee /admin/games/new exists and never 404s
try:
    vf = app.view_functions
except Exception:
    vf = {}

if isinstance(vf, dict) and 'admin_games_new' not in vf:
    @app.route('/admin/games/new', methods=['GET'], endpoint='admin_games_new')
    @admin_required
    def __admin_games_new():
        try:
            return render_template('admin/games/new.html')
        except _JinjaTemplateNotFound:
            return _games_inline_new_form()
        except Exception:
            return _games_inline_new_form()

# Force /admin/games/<id>/edit to always render a full form on GET, and save on POST
# FIX: duplicate edit-route decorator removed
# @app.route('/admin/games/<int:game_id>/edit', methods=['GET','POST'], endpoint='admin_games_edit')
@admin_required
def __admin_games_edit_forced(game_id: int):
    if request.method == 'POST':
        if _games_save(game_id, request.form):
            try: flash("گۆڕانکاریەکان پاشەکەوت کران.", "success")
            except Exception: pass
            return redirect(url_for('admin_games'))
        try: flash("نەتوانرا پاشەکەوت بکرێت.", "error")
        except Exception: pass
    game = _games_fetch(game_id)
    try:
        return render_template('admin/games/edit.html', game=game)
    except Exception:
        # inline fallback form
        active_checked = "checked" if game.get("is_active") else ""
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
            f"<label style='display:flex;align-items:center;gap:.5rem'><input type='checkbox' name='is_active' value='1' {active_checked}> چالاک</label>"
            "<div style='margin-top:10px'><button>پاشەکەوت</button> <a href='/admin/games'>گەڕانەوە</a></div>"
            "</form>"
        )

# Aliases and catch-all to avoid 404s
@app.route('/admin/games/<int:game_id>/config', methods=['GET','POST'])
@admin_required
def __admin_games_config_alias(game_id: int):
    return redirect(url_for('admin_games_edit', game_id=game_id))

@app.route('/admin/games/<int:game_id>/<path:subpath>', methods=['GET','POST'])
@admin_required
def __admin_games_catch_all(game_id: int, subpath: str):
    sp = (subpath or '').strip('/').lower()
    if sp in {'config','configuration','settings','options','setup','manage','management'}:
        return redirect(url_for('admin_games_edit', game_id=game_id))
    if sp == 'edit':
        return redirect(url_for('admin_games_edit', game_id=game_id))
    if sp == 'play':
        return redirect(f"/games/{int(game_id)}/play")
    # help page
    return (
        "<!doctype html><meta charset='utf-8'>"
        f"<h3>ڕێگای نەناسراو: <code>{subpath}</code></h3>"
        f"<ul><li><a href='/admin/games/{game_id}/edit'>دەستکاری</a></li>"
        f"<li><a href='/games/{game_id}/play' target='_blank'>بەزاندن</a></li>"
        f"<li><a href='/admin/games'>⟵ گەڕانەوە</a></li></ul>"
    )

# Dev helper: list routes
if '__routes' not in app.view_functions:
    @app.route("/__routes")
    def __routes():
        try:
            rows = []
            with app.app_context():
                for rule in app.url_map.iter_rules():
                    methods = ",".join(sorted(rule.methods - {"HEAD","OPTIONS"}))
                    rows.append(f"<tr><td>{rule.rule}</td><td>{rule.endpoint}</td><td>{methods}</td></tr>")
            table = "<table border='1' cellpadding='6'><tr><th>Rule</th><th>Endpoint</th><th>Methods</th></tr>" + "".join(rows) + "</table>"
            return "<h3>Registered Routes</h3>" + table
        except Exception as e:
            return f"<pre>{e}</pre>", 500
# ==== END AUTO-PATCH (Games Admin) ====

# === SAFE REBIND for /admin/games/<id>/edit (no duplicate endpoints) ===
try:
    from functools import wraps
except Exception:
    pass

def __forced_admin_games_edit(game_id: int):
    # --- هەمان لاجیکەکەت لێرە بنووسە/بێت (کە لە وەشانی پێشوو بوو) ---
    # GET -> render template (fallback inline if needed)
    # POST -> save (UPDATE/INSERT) then redirect to admin_games
    game = _games_fetch(game_id)
    if request.method == "POST":
        if _games_save(game_id, request.form):
            try: flash("گۆڕانکاریەکان پاشەکەوت کران.", "success")
            except Exception: pass
            return redirect(url_for("admin_games"))
        try: flash("نەتوانرا پاشەکەوت بکرێت.", "error")
        except Exception: pass
    try:
        return render_template("admin/games/edit.html", game=game)
    except Exception:
        active_checked = "checked" if game.get("is_active") else ""
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
            f"<label style='display:flex;align-items:center;gap:.5rem'><input type='checkbox' name='is_active' value='1' {active_checked}> چالاک</label>"
            "<div style='margin-top:10px'><button>پاشەکەوت</button> <a href='/admin/games'>گەڕانەوە</a></div>"
            "</form>"
        )

# — registration logic without duplicate —
try:
    if 'admin_games_edit' in app.view_functions:
        # endpoint already exists -> just replace the view function
        app.view_functions['admin_games_edit'] = admin_required(__forced_admin_games_edit)
    else:
        # endpoint missing -> avoid duplicate registration to prevent AssertionError
        # You can manually add the rule elsewhere if needed, but we skip here to stay safe.
        print("NOTE: admin_games_edit endpoint not yet registered; skipping auto add to avoid duplicates.")
except Exception as e:
    print("SAFE REBIND admin_games_edit failed:", e)
# === END SAFE REBIND ===
# ===== Payout helpers & routes (DROP-IN BLOCK) =====
# Put this AFTER your imports and AFTER you have get_db(), app, session, flash, jsonify, render_template available.

import json

def _get_setting(key, default=None):
    con = get_db(); c = con.cursor()
    try:
        r = c.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
        return (r['value'] if r else default)
    finally:
        con.close()

def _ensure_payout_tables():
    con = get_db()
    c = con.cursor()
    try:
        c.execute("""
CREATE TABLE IF NOT EXISTS payout_providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind in ('bank','mobile')),
    is_active INTEGER DEFAULT 1,
    fields_json TEXT DEFAULT '{}'
)
""")
        c.execute("""
CREATE TABLE IF NOT EXISTS user_payout_methods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    provider_id INTEGER NOT NULL,
    account_json TEXT NOT NULL,
    is_default INTEGER DEFAULT 1,
    status TEXT DEFAULT 'unverified',
    verified_at TEXT
)
""")
        # payout_requests table should already exist in your app; if not, uncomment next block:
        # c.execute("""
        # CREATE TABLE IF NOT EXISTS payout_requests (
        #     id INTEGER PRIMARY KEY AUTOINCREMENT,
        #     user_id INTEGER,
        #     method TEXT,
        #     provider TEXT,
        #     account TEXT,
        #     points INTEGER,
        #     fee_points INTEGER DEFAULT 0,
        #     status TEXT DEFAULT 'pending',
        #     created_at TEXT,
        #     processed_at TEXT
        # )
        # """)
        con.commit()
    finally:
        con.close()

@app.route("/api/payout/provider/<int:pid>/fields")
def api_payout_provider_fields(pid):
    _ensure_payout_tables()
    con = get_db(); c = con.cursor()
    try:
        r = c.execute("SELECT fields_json FROM payout_providers WHERE id=? AND is_active=1", (pid,)).fetchone()
        fields = json.loads(r['fields_json'] or "{}") if r else {}
        return jsonify(fields)
    finally:
        con.close()

@app.route("/wallet/payout", methods=["GET", "POST"])
def wallet_payout():
    # --- auth check ---
    uid = session.get("user_id")
    if not uid:
        try:
            flash("تکایە بچۆ ژوورەوە.", "error")
        except Exception:
            pass
        return redirect(url_for("login")) if "login" in globals() else redirect("/")

    # --- ensure payout tables exist (providers & user methods) ---
    try:
        _ensure_payout_tables()
    except NameError:
        # اگر هێلپەری _ensure_payout_tables لە پرۆژەکەت نییە، دواتر پێم بڵێ تا زیادم بکەم
        pass

    con = get_db(); c = con.cursor()
    try:
        # --- ensure profiles & wallet_points exist (safe, idempotent) ---
        c.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            wallet_points INTEGER DEFAULT 0
        )
        """)
        info = c.execute("PRAGMA table_info(profiles)").fetchall()
        have_wallet_col = any((row[1] if isinstance(row, tuple) else row[1]).lower() == "wallet_points" for row in info)
        if not have_wallet_col:
            c.execute("ALTER TABLE profiles ADD COLUMN wallet_points INTEGER DEFAULT 0")
        c.execute("UPDATE profiles SET wallet_points = COALESCE(wallet_points, 0)")

        # --- settings (with defaults) ---
        def _setting(k, dflt):
            try:
                v = _get_setting(k, dflt)
                return int(v) if str(v).isdigit() else dflt
            except Exception:
                return dflt

        money_per_point   = _setting("money_per_point",   10)
        min_payout_points = _setting("min_payout_points", 100)
        payout_fee_points = _setting("payout_fee_points", 5)

        # --- balance ---
        r = c.execute("SELECT wallet_points FROM profiles WHERE user_id=?", (uid,)).fetchone()
        balance = int((r[0] if isinstance(r, tuple) else r["wallet_points"]) or 0) if r else 0


        if request.method == "POST":
            # inputs
            provider_id = int(request.form.get("provider_id") or 0)
            points = int(request.form.get("points") or 0)

            # validate points
            if points < min_payout_points:
                flash("کەمترە لە کەمترین پۆینت.", "error")
                return redirect(url_for("wallet_payout"))

            need = points + payout_fee_points
            if balance < need:
                flash("پۆینتەکانت بەھێز نیەن.", "error")
                return redirect(url_for("wallet_payout"))

            # provider
            prov = c.execute(
                "SELECT id,name,kind,fields_json FROM payout_providers WHERE id=? AND is_active=1",
                (provider_id,)
            ).fetchone()
            if not prov:
                flash("سەرچاوە نەدۆزرایەوە/ناچالاکە.", "error")
                return redirect(url_for("wallet_payout"))

            # validate dynamic fields
            import json, re as _re
            fields = json.loads((prov["fields_json"] if not isinstance(prov, tuple) else prov[3]) or "{}")
            account = {}
            for key, spec in fields.items():
                val = (request.form.get(f"acc_{key}") or "").strip()
                if spec.get("required") and not val:
                    flash(f"خانە {key} دەبێت پڕ بکرێت.", "error")
                    return redirect(url_for("wallet_payout"))
                pat = spec.get("pattern")
                if pat and val and not _re.match(pat, val):
                    flash(f"نرخی {key} نادروستە.", "error")
                    return redirect(url_for("wallet_payout"))
                account[key] = val

            # save user method (default)
            c.execute(
                "INSERT INTO user_payout_methods(user_id, provider_id, account_json, is_default, status) VALUES(?,?,?,?,?)",
                (uid, (prov["id"] if not isinstance(prov, tuple) else prov[0]), json.dumps(account), 1, "unverified")
            )

            # create payout request (pending)
            main_acc = account.get("mobile") or account.get("iban") or account.get("card") or json.dumps(account)
            c.execute(
                """INSERT INTO payout_requests(user_id, method, provider, account, points, fee_points, status, created_at)
                   VALUES(?,?,?,?,?,?, 'pending', datetime('now'))""",
                (
                    uid,
                    (prov["kind"] if not isinstance(prov, tuple) else prov[2]),
                    (prov["name"] if not isinstance(prov, tuple) else prov[1]),
                    main_acc, points, payout_fee_points
                )
            )

            con.commit()
            flash("داواکاری پەرەدان پێشکەش کرا. چاوەڕێی پەسەندکردنی ئەدمین بکە.", "success")
            return redirect(url_for("wallet_payout"))

        # GET: providers & methods
        providers = c.execute(
            "SELECT id,name,kind,is_active,fields_json FROM payout_providers WHERE is_active=1 ORDER BY id DESC"
        ).fetchall()
        methods = c.execute(
            """SELECT m.id, m.provider_id, m.account_json, m.is_default, m.status,
                      p.name as provider_name, p.kind as provider_kind FROM user_payout_methods m
               JOIN payout_providers p ON p.id = m.provider_id
               WHERE m.user_id=? ORDER BY m.id DESC""",
            (uid,)
        ).fetchall()

        return render_template(
            "wallet_payout.html",
            balance=balance,
            money_per_point=money_per_point,
            min_payout_points=min_payout_points,
            payout_fee_points=payout_fee_points,
            providers=providers,
            methods=methods
        )
    finally:
        con.close()

# ===== end payout block =====
# --- [AUTO-ADDED] profiles wallet helpers (safe) ---
def _ensure_profiles_wallet():
    con = get_db(); c = con.cursor()
    try:
        # خشتەی بنەڕەتی پرۆژەکەت: user_id PRIMARY KEY هەیە
        c.execute("""
        CREATE TABLE IF NOT EXISTS profiles(
            user_id INTEGER PRIMARY KEY,
            wallet_points INTEGER NOT NULL DEFAULT 0
        )
        """)
        # دڵنیابە ستوونی wallet_points هەیە
        info = c.execute("PRAGMA table_info(profiles)").fetchall()
        have_wallet = any((row["name"] if isinstance(row, sqlite3.Row) else row[1]) == "wallet_points" for row in info)
        if not have_wallet:
            c.execute("ALTER TABLE profiles ADD COLUMN wallet_points INTEGER NOT NULL DEFAULT 0")
        c.execute("UPDATE profiles SET wallet_points = COALESCE(wallet_points, 0)")
        con.commit()
    finally:
        con.close()

def _get_balance(uid):
    con = get_db(); c = con.cursor()
    try:
        # هەوڵی wallet_points
        try:
            r = c.execute("SELECT wallet_points FROM profiles WHERE id=?", (uid,)).fetchone()
            if r is not None:
                v = r[0] if isinstance(r, tuple) else (r["wallet_points"] if "wallet_points" in r.keys() else None)
                if v is not None:
                    return int(v or 0)
        except Exception:
            pass
        # بەپشتیوانی: ئەگەر ستون بە ناوی تر بوو (نمونە points)
        try:
            r = c.execute("SELECT points FROM profiles WHERE id=?", (uid,)).fetchone()
            if r is not None:
                v = r[0] if isinstance(r, tuple) else (r["points"] if "points" in r.keys() else None)
                if v is not None:
                    return int(v or 0)
        except Exception:
            pass
        return 0
    finally:
        con.close()
# --- [END AUTO-ADDED] ---
# ===== Market feature (DROP-IN PATCH) =====
# Requirements: app, get_db, render_template, request, session, flash, redirect, url_for, jsonify available.
# This patch adds:
#   - _ensure_market_tables()
#   - _is_admin() helper
#   - _get_balance() and _change_points() helpers (safe, no-op if columns missing)
#   - /market (GET list, POST buy)
#   - /admin/market (add/toggle/delete items)
#   - /admin/stats (admin-only market stats)
#
# HOW TO INSTALL:
# 1) Paste this whole block anywhere after your imports in app.py.
# 2) Drop the three templates into your templates/ folder.
# 3) Add a link to /market in your navbar (e.g., <a href="{{ url_for('market') }}">بازار</a>).
# ===========================================

import json, sqlite3


def _is_admin():
    try:
        return _has_role('admin') or bool(session.get('is_admin') or session.get('admin'))
    except Exception:
        return _has_role('admin')


def _ensure_market_tables():
    con = get_db(); c = con.cursor()
    try:
        c.execute("""
CREATE TABLE IF NOT EXISTS market_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price_points INTEGER NOT NULL,
    stock INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    meta_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now'))
)
""")
        c.execute("""
CREATE TABLE IF NOT EXISTS market_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    item_id INTEGER NOT NULL,
    qty INTEGER NOT NULL,
    points_total INTEGER NOT NULL,
    status TEXT DEFAULT 'pending',
    phone TEXT,
    address TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
)
""")

        con.commit()
    finally:
        con.close()

def _get_balance(uid):
    con = get_db(); c = con.cursor()
    try:
        # Try wallet_points (preferred)
        try:
            r = c.execute("SELECT wallet_points FROM profiles WHERE user_id=?", (uid,)).fetchone()
            if r is not None:
                v = r[0] if not isinstance(r, sqlite3.Row) else r["wallet_points"]
                return int(v or 0)
        except Exception:
            pass
        # Fallback: id column schema
        try:
            r = c.execute("SELECT wallet_points FROM profiles WHERE id=?", (uid,)).fetchone()
            if r is not None:
                v = r[0] if not isinstance(r, sqlite3.Row) else r["wallet_points"]
                return int(v or 0)
        except Exception:
            pass
        # Fallback: points column
        try:
            r = c.execute("SELECT points FROM profiles WHERE user_id=?", (uid,)).fetchone()
            if r is not None:
                v = r[0] if not isinstance(r, sqlite3.Row) else r["points"]
                return int(v or 0)
        except Exception:
            pass
        return 0
    finally:
        con.close()

def _change_points(uid, delta, note="market"):
    con = get_db(); c = con.cursor()
    try:
        # Ensure profile row exists
        c.execute("INSERT OR IGNORE INTO profiles(user_id, wallet_points) VALUES(?, COALESCE((SELECT wallet_points FROM profiles WHERE user_id=?),0))", (uid, uid))
        # Update wallet_points (user_id schema)
        c.execute("UPDATE profiles SET wallet_points = COALESCE(wallet_points,0) + ? WHERE user_id=?", (delta, uid))
        # Try id schema too (if user_id path didn't affect any row)
        if c.rowcount == 0:
            c.execute("UPDATE profiles SET wallet_points = COALESCE(wallet_points,0) + ? WHERE id=?", (delta, uid))
        # Optionally log in wallet_transactions if table exists
        try:
            c.execute("INSERT INTO wallet_transactions(user_id, change, type, source, note, created_at) VALUES (?,?,?,?,?,datetime('now'))",
                      (uid, delta, 'market', 'market', note))
        except Exception:
            pass
        con.commit()
    finally:
        con.close()

@app.route("/market", methods=["GET", "POST"])
def market():
    _ensure_market_tables()
    uid = session.get("user_id")
    if not uid:
        try: flash("تکایە بچۆ ژوورەوە.", "error")
        except Exception: pass
        return redirect(url_for("login")) if "login" in globals() else redirect("/")
    con = get_db(); c = con.cursor()
    try:
        if request.method == "POST":
            item_id = int(request.form.get("item_id") or 0)
            qty = max(1, int(request.form.get("qty") or 1))
            item = c.execute("SELECT id,name,price_points,stock,meta_json FROM market_items WHERE id=? AND is_active=1", (item_id,)).fetchone()
            if not item:
                flash("بەرهەم نەدۆزرایەوە/ناچالاکە.", "error")
                return redirect(url_for("market"))
            price = int(item["price_points"] if isinstance(item, sqlite3.Row) else item[2])
            stock = int(item["stock"] if isinstance(item, sqlite3.Row) else item[3])
            if qty > stock:
                flash("کۆی بەرھەم کەمە.", "error")
                return redirect(url_for("market"))
            total = price * qty
            bal = _get_balance(uid)
            if bal < total:
                flash("پۆینتەکانت بەھێز نیەن.", "error")
                return redirect(url_for("market"))
            # Deduct points and save order
            _change_points(uid, -total, note=f"buy {qty}x #{item_id}")
            c.execute("UPDATE market_items SET stock=stock-? WHERE id=?", (qty, item_id))
            c.execute("INSERT INTO market_orders(user_id,item_id,qty,points_total) VALUES(?,?,?,?)", (uid, item_id, qty, total))
            _ensure_market_tracking()
            con.commit()
            flash("کڕین سەرکەوتوو بوو.", "success")
            return redirect(url_for("market"))

        items = c.execute("SELECT id,name,price_points,stock,meta_json FROM market_items WHERE is_active=1 ORDER BY id DESC").fetchall()
        balance = _get_balance(uid)
        return render_template("market.html", items=items, balance=balance)
    finally:
        con.close()

@app.route("/admin/market", methods=["GET","POST"])
def admin_market():
    if not _is_admin():
        return ("Not authorized", 403)
    _ensure_market_tables()
    con = get_db(); c = con.cursor()
    try:
        if request.method == "POST":
            action = (request.form.get("action") or "").strip()
            if action == "add":
                name = (request.form.get("name") or "").strip()
                price_points = int(request.form.get("price_points") or 0)
                stock = int(request.form.get("stock") or 0)
                meta_json = request.form.get("meta_json") or "{}"
                if not name or price_points <= 0:
                    flash("ناو/نرخ هەڵەیە.", "error")
                else:
                    try:
                        json.loads(meta_json)
                    except Exception:
                        meta_json = "{}"
                    c.execute("INSERT INTO market_items(name,price_points,stock,is_active,meta_json) VALUES(?,?,?,?,?)",
                              (name, price_points, stock, 1, meta_json))
                    con.commit()
                    flash("بەرهەم زیادکرا.", "success")
                return redirect(url_for("admin_market"))
        items = c.execute("SELECT * FROM market_items ORDER BY id DESC").fetchall()
        orders = c.execute("""SELECT o.id,o.user_id,o.item_id,o.qty,o.points_total,o.created_at,i.name FROM market_orders o JOIN market_items i ON i.id=o.item_id ORDER BY o.id DESC LIMIT 50""").fetchall()
        return render_template("admin_market.html", items=items, orders=orders)
    finally:
        con.close()

@app.post("/admin/market/<int:item_id>/toggle")
def admin_market_toggle(item_id):
    if not _is_admin():
        return ("Not authorized", 403)
    con = get_db(); c = con.cursor()
    try:
        c.execute("UPDATE market_items SET is_active = CASE is_active WHEN 1 THEN 0 ELSE 1 END WHERE id=?", (item_id,))
        con.commit()
        return redirect(url_for("admin_market"))
    finally:
        con.close()

@app.post("/admin/market/<int:item_id>/delete")
def admin_market_delete(item_id):
    if not _is_admin():
        return ("Not authorized", 403)
    con = get_db(); c = con.cursor()
    try:
        c.execute("DELETE FROM market_items WHERE id=?", (item_id,))
        con.commit()
        return redirect(url_for("admin_market"))
    finally:
        con.close()

@app.route("/admin/stats")
def admin_stats():
    if not _is_admin():
        return ("Not authorized", 403)
    _ensure_market_tables()
    con = get_db(); c = con.cursor()
    try:
        s1 = c.execute("SELECT COUNT(*) AS cnt, COALESCE(SUM(points_total),0) AS pts FROM market_orders").fetchone()
        top = c.execute("""SELECT i.name, SUM(o.qty) AS q, SUM(o.points_total) AS pts FROM market_orders o JOIN market_items i ON i.id=o.item_id
                           GROUP BY o.item_id ORDER BY q DESC LIMIT 10""").fetchall()
        last = c.execute("""SELECT o.id, o.user_id, i.name, o.qty, o.points_total, o.created_at FROM market_orders o JOIN market_items i ON i.id=o.item_id
                            ORDER BY o.id DESC LIMIT 25""").fetchall()
        return render_template("admin_stats.html", orders_total=(s1["cnt"] if isinstance(s1, sqlite3.Row) else s1[0]),
                               points_total=(s1["pts"] if isinstance(s1, sqlite3.Row) else s1[1]),
                               top=top, last=last)
    finally:
        con.close()
# ===== END Market feature =====
# ===== Market edit + meta support (ADD THIS) =====
import json, sqlite3

@app.get("/admin/market/<int:item_id>/edit")
def admin_market_edit(item_id):
    if not (_is_admin() if "_is_admin" in globals() else session.get("is_admin") or session.get("admin")):
        return ("Not authorized", 403)
    con = get_db(); c = con.cursor()
    try:
        it = c.execute("SELECT id,name,price_points,stock,is_active,meta_json FROM market_items WHERE id=?", (item_id,)).fetchone()
        if not it:
            return ("Item not found", 404)
        # بە شێوەی dict بۆ ئاسانی لە تێمپلێتدا
        d = dict(it) if isinstance(it, sqlite3.Row) else {
            "id": it[0], "name": it[1], "price_points": it[2], "stock": it[3], "is_active": it[4], "meta_json": it[5]
        }
        # هەوڵی پارسکردنی JSON
        try:
            d["meta"] = json.loads(d.get("meta_json") or "{}")
        except Exception:
            d["meta"] = {}
        return render_template("admin_market_edit.html", item=d)
    finally:
        con.close()

@app.post("/admin/market/<int:item_id>/edit")
def admin_market_edit_save(item_id):
    if not (_is_admin() if "_is_admin" in globals() else session.get("is_admin") or session.get("admin")):
        return ("Not authorized", 403)
    name = (request.form.get("name") or "").strip()
    price_points = int(request.form.get("price_points") or 0)
    stock = int(request.form.get("stock") or 0)
    is_active = 1 if request.form.get("is_active") else 0
    meta_json = request.form.get("meta_json") or "{}"
    # پشتگیری: ئەگەر JSON هەڵە بوو، بە `{}` ده‌كه‌ین
    try:
        json.loads(meta_json)
    except Exception:
        meta_json = "{}"

    con = get_db(); c = con.cursor()
    try:
        c.execute("""UPDATE market_items
                     SET name=?, price_points=?, stock=?, is_active=?, meta_json=?
                     WHERE id=?""",
                  (name, price_points, stock, is_active, meta_json, item_id))
        con.commit()
        try: flash("گۆڕانکاری پاشەکەوت کرا.", "success")
        except: pass
        return redirect(url_for("admin_market"))
    finally:
        con.close()

# (اختیاری، بە باشتر بینین لە «بازار») — لە فانكشنی /market هەمان پێشـهەنگی بكە:
# items = c.execute("SELECT id,name,price_points,stock,meta_json FROM market_items WHERE is_active=1 ORDER BY id DESC").fetchall()
# items_view = []
# for it in items:
#     d = dict(it) if isinstance(it, sqlite3.Row) else {"id": it[0], "name": it[1], "price_points": it[2], "stock": it[3], "meta_json": it[4]}
#     try: d["meta"] = json.loads(d.get("meta_json") or "{}")
#     except: d["meta"] = {}
#     items_view.append(d)
# return render_template("market.html", items=items_view, balance=_get_balance(uid))
# ===== END patch =====
# ===== Market: image upload + extra meta + richer orders (ADD) =====
import os
from werkzeug.utils import secure_filename
app.config.setdefault("UPLOAD_FOLDER", os.path.join(app.root_path, "static", "uploads"))
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
app.config.setdefault("MAX_CONTENT_LENGTH", 10 * 1024 * 1024)  # 10MB
import os, json, sqlite3
from werkzeug.utils import secure_filename

def _save_uploaded_image(file):
    if not file or not getattr(file, "filename", ""):
        return None
    fname = secure_filename(file.filename)
    if not fname:
        return None
    base, ext = os.path.splitext(fname)
    if ext.lower() not in {".jpg",".jpeg",".png",".webp",".gif"}:
        return None
    i = 1
    upload_folder = app.config.get("UPLOAD_FOLDER")
    if not upload_folder:
        upload_folder = os.path.join(app.root_path, "static", "uploads")
        os.makedirs(upload_folder, exist_ok=True)
        app.config["UPLOAD_FOLDER"] = upload_folder
    out = os.path.join(upload_folder, fname)
    while os.path.exists(out):
        fname = f"{base}_{i}{ext}"
        out = os.path.join(upload_folder, fname)
        i += 1
    file.save(out)
    # 🔧 FIX: escape backslash correctly
    rel = os.path.relpath(out, app.root_path).replace("\\", "/")
    url = rel if rel.startswith("/") else "/" + rel
    return url

import os, json, sqlite3
from werkzeug.utils import secure_filename

def _save_uploaded_image(file):
    if not file or not getattr(file, "filename", ""):
        return None
    fname = secure_filename(file.filename)
    if not fname:
        return None
    base, ext = os.path.splitext(fname)
    if ext.lower() not in {".jpg",".jpeg",".png",".webp",".gif"}:
        return None
    i = 1
    upload_folder = app.config.get("UPLOAD_FOLDER")
    if not upload_folder:
        upload_folder = os.path.join(app.root_path, "static", "uploads")
        os.makedirs(upload_folder, exist_ok=True)
        app.config["UPLOAD_FOLDER"] = upload_folder
    out = os.path.join(upload_folder, fname)
    while os.path.exists(out):
        fname = f"{base}_{i}{ext}"
        out = os.path.join(upload_folder, fname)
        i += 1
    file.save(out)
    rel = out.split(app.root_path)[-1].replace("\\","/")
    url = rel if rel.startswith("/") else "/" + rel
    return url

def __admin_market_add_handler__(request, c, con):
    name = (request.form.get("name") or "").strip()
    price_points = int(request.form.get("price_points") or 0)
    stock = int(request.form.get("stock") or 0)
    desc = (request.form.get("desc") or "").strip()
    category = (request.form.get("category") or "").strip()
    condition = (request.form.get("condition") or "").strip()
    model = (request.form.get("model") or "").strip()
    meta_json_text = request.form.get("meta_json") or "{}"
    img_file = request.files.get("image")

    try:
        meta = json.loads(meta_json_text)
        if not isinstance(meta, dict):
            meta = {}
    except Exception:
        meta = {}
    if desc: meta["desc"] = desc
    if category: meta["category"] = category
    if condition in ("new","used"): meta["condition"] = condition
    if model: meta["model"] = model

    img_url = _save_uploaded_image(img_file)
    if img_url: meta["img"] = img_url

    if not name or price_points <= 0:
        try: flash("ناو/نرخ هەڵەیە.", "error")
        except: pass
    else:
        c.execute("INSERT INTO market_items(name,price_points,stock,is_active,meta_json) VALUES(?,?,?,?,?)",
                  (name, price_points, stock, 1, json.dumps(meta, ensure_ascii=False)))
        con.commit()
        try: flash("بەرهەم زیادکرا.", "success")
        except: pass

def __admin_market_edit_save__(item_id, request, c, con):
    name = (request.form.get("name") or "").strip()
    price_points = int(request.form.get("price_points") or 0)
    stock = int(request.form.get("stock") or 0)
    is_active = 1 if request.form.get("is_active") else 0
    desc = (request.form.get("desc") or "").strip()
    category = (request.form.get("category") or "").strip()
    condition = (request.form.get("condition") or "").strip()
    model = (request.form.get("model") or "").strip()
    meta_json = request.form.get("meta_json") or "{}"
    img_file = request.files.get("image")

    orig = c.execute("SELECT meta_json FROM market_items WHERE id=?", (item_id,)).fetchone()
    try:
        base_meta = json.loads((orig["meta_json"] if isinstance(orig, sqlite3.Row) else orig[0]) or "{}") if orig else {}
        if not isinstance(base_meta, dict): base_meta = {}
    except Exception:
        base_meta = {}

    try:
        new_meta = json.loads(meta_json) if meta_json else {}
        if not isinstance(new_meta, dict): new_meta = {}
    except Exception:
        new_meta = {}

    meta = {**base_meta, **new_meta}
    if desc: meta["desc"] = desc
    if category: meta["category"] = category
    if condition in ("new","used"): meta["condition"] = condition
    if model: meta["model"] = model

    img_url = _save_uploaded_image(img_file)
    if img_url: meta["img"] = img_url

    c.execute("""UPDATE market_items
                 SET name=?, price_points=?, stock=?, is_active=?, meta_json=?
                 WHERE id=?""", (name, price_points, stock, is_active, json.dumps(meta, ensure_ascii=False), item_id))
    con.commit()

def __admin_market_orders_query__(c):
    try:
        cols = [r[1] for r in c.execute("PRAGMA table_info(profiles)")]
        has_username = "username" in [str(x).lower() for x in cols]
    except Exception:
        has_username = False

    if has_username:
        q = """SELECT o.id,o.user_id, COALESCE(p.username, '') AS username,
                      o.item_id,o.qty,o.points_total,o.created_at,
                      i.name, i.meta_json FROM market_orders o
               LEFT JOIN profiles p ON p.user_id=o.user_id
               JOIN market_items i ON i.id=o.item_id
               ORDER BY o.id DESC LIMIT 50"""
    else:
        q = """SELECT o.id,o.user_id,'' AS username,
                      o.item_id,o.qty,o.points_total,o.created_at,
                      i.name, i.meta_json FROM market_orders o
               JOIN market_items i ON i.id=o.item_id
               ORDER BY o.id DESC LIMIT 50"""
    return c.execute(q).fetchall()
# ===== END patch =====
# --- Jinja filter: fromjson (safe) ---
import json
from markupsafe import Markup  # هەرچی بوو، بەکاردێت ئەگەر پەسەندت بۆ pretty چاپ

@app.template_filter("fromjson")
def jinja_fromjson(value):
    """
    Parse JSON string into Python object (dict/list).
    Returns {} on error. If already dict/list, return as-is.
    """
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return {}
# ===== NOTIFY: core + one-time registration =====
from flask import request, redirect, url_for, flash, session

def _is_admin():
    try:
        if '_has_role' in globals():
            try:
                if _has_role('admin') or _has_role('superadmin'):
                    return True
            except Exception:
                pass
        return bool(session.get('is_admin') or session.get('admin'))
    except Exception:
        return False

def _admin_order_notify_core(order_id: int):
    if not _is_admin():
        return ("Not authorized", 403)
    con = get_db(); c = con.cursor()
    try:
        row = c.execute("SELECT * FROM market_orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            return ("Order not found", 404)
        ok = False
        try:
            order = {k: row[k] for k in getattr(row, "keys", lambda: [])()}
            if '_notify_buyer' in globals():
                ok = bool(_notify_buyer(order, reason="manual"))
        except Exception:
            pass
        try:
            flash("نۆتیفیکەیشن نێردرا." if ok else "هەوڵی ناردن شکستی هێنا.", "info" if ok else "error")
        except Exception:
            pass
        return redirect(url_for("admin_market") if "admin_market" in app.view_functions else "/admin/market")
    finally:
        con.close()

def _wire_notify_once():
    ep = "admin_market_order_notify"
    # ڕەوتەکە تەنیا یەکجار تۆمار بکە
    if ep not in app.view_functions:
        app.add_url_rule(
            "/admin/market/order/<int:order_id>/notify",
            endpoint=ep,
            view_func=lambda order_id: _admin_order_notify_core(order_id),
            methods=["POST"],
        )

# ڕادەستکردن لە کاتی import
try:
    _wire_notify_once()
except Exception as e:
    print("wire notify error:", e)
# ===== END =====


# ===== Bootstrap for Flask 3.x (no before_first_request) =====
try:
    _MARKET_BOOTSTRAPPED
except NameError:
    _MARKET_BOOTSTRAPPED = False

@app.before_request
def _boot_once_v3():
    global _MARKET_BOOTSTRAPPED
    if _MARKET_BOOTSTRAPPED:
        return
    try:
        try:
            _ensure_market_orders_table()
        except Exception:
            pass
        try:
            _market_orders_migrate()
        except Exception:
            pass
    finally:
        _MARKET_BOOTSTRAPPED = True
# ===== /Bootstrap =====



def _ensure_market_orders_table():
    con = get_db(); c = con.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS market_orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER,
        user_id INTEGER,
        buyer_name TEXT,
        qty INTEGER,
        total_points INTEGER,
        member_code TEXT,
        status TEXT,
        address TEXT,
        phone TEXT,
        tracking_code TEXT,
        notes TEXT,
        created_at TEXT,
        updated_at TEXT
    )""")
    con.commit(); con.close()




def _market_orders_migrate():
    con = get_db(); c = con.cursor()
    try:
        cols = {r[1] for r in c.execute("PRAGMA table_info(market_orders)").fetchall()}
        wanted = [
            ("item_id","INTEGER"),
            ("user_id","INTEGER"),
            ("buyer_name","TEXT"),
            ("member_code","TEXT"),
            ("qty","INTEGER"),
            ("total_points","INTEGER"),
            ("status","TEXT"),
            ("address","TEXT"),
            ("phone","TEXT"),
            ("tracking_code","TEXT"),
            ("notes","TEXT"),
            ("created_at","TEXT"),
            ("updated_at","TEXT"),
        ]
        for name, typ in wanted:
            if name not in cols:
                c.execute(f"ALTER TABLE market_orders ADD COLUMN {name} {typ}")
        con.commit()
    finally:
        con.close()
def _order_dynamic_insert(c, item_id, uid, buyer_name, qty, total):
    cols_info = c.execute("PRAGMA table_info(market_orders)").fetchall()
    existing = {row[1] for row in cols_info}
    payload = {
        "item_id": item_id,
        "user_id": uid,
        "buyer_name": buyer_name,
        "qty": qty,
        "total_points": total,
        "status": "ordered",
        "address": "",
        "phone": "",
        "tracking_code": "",
        "notes": "",
        "created_at": None,
        "updated_at": None,
    }
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    if "created_at" in existing: payload["created_at"] = now
    if "updated_at" in existing: payload["updated_at"] = now
    cols = [k for k in payload if k in existing]
    vals = [payload[k] for k in cols]
    qmarks = ",".join(["?"]*len(cols))
    sql = f"INSERT INTO market_orders({','.join(cols)}) VALUES({qmarks})"
    c.execute(sql, tuple(vals))
@app.route("/admin/roles", methods=["GET","POST"])
def admin_roles():
    if not _is_superadmin():
        return ("Not authorized", 403)
    _ensure_admin_roles_table_and_seed()
    con = get_db(); c = con.cursor()
    try:
        if request.method == "POST":
            action = (request.form.get("action") or "").strip()
            email = (request.form.get("email") or "").strip()
            role  = (request.form.get("role") or "").strip()
            if action == "add" and email and role in ("admin","superadmin"):
                u = c.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
                if u:
                    uid = u[0] if isinstance(u, tuple) else (u["id"] if hasattr(u, "keys") and "id" in u.keys() else None)
                    if uid is not None:
                        c.execute("INSERT OR REPLACE INTO admin_roles(user_id, role) VALUES(?,?)", (uid, role))
                        con.commit()
                        flash("ڕۆڵ زیاد/نوێکرایەوە.", "success")
                else:
                    flash("بەکارهێنەر بەو ئیمەیڵە نەدۆزرایەوە.", "error")
            return redirect(url_for("admin_roles"))
        users = c.execute("SELECT id,username,email FROM users ORDER BY id DESC LIMIT 200").fetchall()
        roles  = c.execute("SELECT user_id,role FROM admin_roles").fetchall()
        role_map = {}
        for r in roles:
            if isinstance(r, tuple):
                role_map[r[0]] = r[1]
            else:
                role_map[r["user_id"]] = r["role"]
        return render_template("admin_roles.html", users=users, role_map=role_map, seed_email="adilask3@gmail.com")
    finally:
        con.close()

@app.post("/admin/roles/<int:user_id>/set")
def admin_roles_set(user_id):
    if not _is_superadmin():
        return ("Not authorized", 403)
    role = (request.form.get("role") or "").strip()
    if role not in ("admin","superadmin"):
        flash("ڕۆڵ نادروستە.", "error")
        return redirect(url_for("admin_roles"))
    _ensure_admin_roles_table_and_seed()
    con = get_db(); c = con.cursor()
    try:
        c.execute("INSERT OR REPLACE INTO admin_roles(user_id, role) VALUES(?,?)", (user_id, role))
        con.commit()
        flash("ڕۆڵ نوێکرایەوە.", "success")
        return redirect(url_for("admin_roles"))
    finally:
        con.close()

@app.post("/admin/roles/<int:user_id>/delete")
def admin_roles_delete(user_id):
    if not _is_superadmin():
        return ("Not authorized", 403)
    _ensure_admin_roles_table_and_seed()
    con = get_db(); c = con.cursor()
    try:
        c.execute("DELETE FROM admin_roles WHERE user_id=?", (user_id,))
        con.commit()
        flash("ڕۆڵ سڕایەوە.", "info")
        return redirect(url_for("admin_roles"))
    finally:
        con.close()

def _rand_code(n=10):
    import random, string
    alphabet = string.ascii_lowercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(n))

def _ensure_market_tracking():
    # Ensure tracking_code column exists on market_orders
    con = get_db(); c = con.cursor()
    try:
        cols = [r[1] if isinstance(r, tuple) else r['name'] for r in c.execute("PRAGMA table_info(market_orders)").fetchall()]
        if 'tracking_code' not in cols:
            c.execute("ALTER TABLE market_orders ADD COLUMN tracking_code TEXT")
            con.commit()
    finally:
        con.close()


@app.get("/track/<code>")
def track_order(code):
    con = get_db(); c = con.cursor()
    try:
        r = c.execute("SELECT id,status,created_at FROM market_orders WHERE tracking_code=?", (code,)).fetchone()
        if not r:
            return render_template("track.html", found=False, code=code)
        if isinstance(r, tuple):
            oid, status, created_at = r
        else:
            oid, status, created_at = r["id"], r["status"], r["created_at"]
        return render_template("track.html", found=True, code=code, order_id=oid, status=status, created_at=created_at)
    finally:
        con.close()

def _app_base_url():
    return os.environ.get('APP_BASE_URL', '').rstrip('/')

def _send_whatsapp(to_phone: str, body: str) -> bool:
    try:
        from twilio.rest import Client
    except Exception:
        return False
    try:
        sid = os.environ.get('TWILIO_ACCOUNT_SID') or app.config.get('TWILIO_ACCOUNT_SID')
        tok = os.environ.get('TWILIO_AUTH_TOKEN') or app.config.get('TWILIO_AUTH_TOKEN')
        frm = os.environ.get('TWILIO_WHATSAPP_FROM') or app.config.get('TWILIO_WHATSAPP_FROM')
        if not (sid and tok and frm and to_phone):
            return False
        cli = Client(sid, tok)
        to = 'whatsapp:' + (to_phone if to_phone.startswith('+') else '+'+to_phone)
        m = cli.messages.create(to=to, from_=frm, body=body)
        return bool(m.sid)
    except Exception:
        return False

def _send_telegram(chat_id: str, body: str) -> bool:
    import urllib.request, urllib.parse
    token = os.environ.get('TELEGRAM_BOT_TOKEN') or app.config.get('TELEGRAM_BOT_TOKEN')
    if not (token and chat_id and body):
        return False
    try:
        data = urllib.parse.urlencode({'chat_id': chat_id, 'text': body}).encode()
        req = urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage', data=data)
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except Exception:
        return False
# --- Notify endpoint (manual), کار دەکات لەگەڵ دوگمەکان ---


# ===================== ALL-IN HOTFIX START =====================
# Clean _ensure_market_tables (no Python keywords inside SQL strings)
def _ensure_market_tables():
    con = get_db(); c = con.cursor()
    try:
        c.execute(
            "CREATE TABLE IF NOT EXISTS market_items ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "name TEXT NOT NULL,"
            "price_points INTEGER NOT NULL DEFAULT 0,"
            "stock INTEGER NOT NULL DEFAULT 0,"
            "meta_json TEXT"
            ")"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS market_orders ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER,"
            "item_id INTEGER NOT NULL,"
            "qty INTEGER NOT NULL DEFAULT 1,"
            "price_points INTEGER NOT NULL DEFAULT 0,"
            "total_points INTEGER NOT NULL DEFAULT 0,"
            "status TEXT DEFAULT 'pending',"
            "phone TEXT,"
            "address TEXT,"
            "meta_json TEXT,"
            "tracking_code TEXT,"
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_market_orders_user ON market_orders(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_market_orders_item ON market_orders(item_id)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_market_orders_tracking ON market_orders(tracking_code)")
        con.commit()
    finally:
        con.close()

# Safe tracking helpers
def _ensure_market_tracking():
    con = get_db(); c = con.cursor()
    try:
        try:
            _ensure_market_tables()
        except Exception:
            pass
        cols = [r[1] for r in c.execute("PRAGMA table_info(market_orders)").fetchall()]
        if 'tracking_code' not in cols:
            c.execute("ALTER TABLE market_orders ADD COLUMN tracking_code TEXT")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_market_orders_tracking ON market_orders(tracking_code)")
        c.execute(
            "CREATE TRIGGER IF NOT EXISTS trg_market_orders_tracking "
            "AFTER INSERT ON market_orders "
            "FOR EACH ROW "
            "WHEN NEW.tracking_code IS NULL "
            "BEGIN "
            "  UPDATE market_orders "
            "    SET tracking_code = lower(hex(randomblob(8))) "
            "    WHERE id = NEW.id; "
            "END;"
        )
        con.commit()
    finally:
        con.close()

# Minimal role helper if missing
if '_is_admin' not in globals():
    def _is_admin():
        try:
            if '_has_role' in globals():
                try:
                    if _has_role('admin'):
                        return True
                except Exception:
                    pass
            return bool(session.get('is_admin') or session.get('admin'))
        except Exception:
            return False

# Notify core if missing
if '_admin_order_notify_core' not in globals():
    from flask import redirect, url_for, flash, request  # noqa: E402
    def _admin_order_notify_core(order_id):
        if not _is_admin():
            return ("Not authorized", 403)
        con = get_db(); c = con.cursor()
        try:
            row = c.execute("SELECT * FROM market_orders WHERE id=?", (order_id,)).fetchone()
            if not row:
                return ("Order not found", 404)
            ok = False
            try:
                order = {k: row[k] for k in getattr(row, "keys", lambda: [])()}
                if '_notify_buyer' in globals():
                    ok = bool(_notify_buyer(order, reason="manual"))
            except Exception:
                pass
            try:
                flash("نۆتیفیکەیشن نێردرا." if ok else "هەوڵی ناردن شکستی هێنا.", "info" if ok else "error")
            except Exception:
                pass
            return redirect(url_for("admin_market") if "admin_market" in app.view_functions else "/")
        finally:
            con.close()

# Register /__routes once
def __routes():
    try:
        rules = sorted([f"{r.rule} -> {r.endpoint}" for r in app.url_map.iter_rules()])
        return "<pre>" + "\n".join(rules) + "</pre>"
    except Exception as e:
        return f"error: {e}", 500

try:
    if "__routes" not in app.view_functions:
        app.add_url_rule("/__routes", endpoint="__routes", view_func=__routes, methods=["GET"])
except Exception:
    pass

# Register notify endpoint ONCE
def _ensure_notify_registered():
    ep = "admin_market_order_notify"
    if ep not in app.view_functions:
        app.add_url_rule(
            "/admin/market/order/<int:order_id>/notify",
            endpoint=ep,
            view_func=lambda order_id: _admin_order_notify_core(order_id),
            methods=["POST"],
        )
_ensure_notify_registered()

# Ensure schema at import
try:
    _ensure_market_tables()
    _ensure_market_tracking()
except Exception:
    pass
# ====================== ALL-IN HOTFIX END ======================
# ===================== MARKET DROP-IN PATCH (place above def market) =====================

# --- Safe helpers (import side) ---
from flask import redirect, url_for, flash, request, session

def _is_admin():
    try:
        # if you have a role system
        if '_has_role' in globals():
            try:
                if _has_role('admin') or _has_role('superadmin'):
                    return True
            except Exception:
                pass
        return bool(session.get('is_admin') or session.get('admin'))
    except Exception:
        return False

# --- Clean tables builder (NO Python keywords inside SQL strings) ---
def _ensure_market_tables():
    con = get_db(); c = con.cursor()
    try:
        # market_items
        c.execute(
            "CREATE TABLE IF NOT EXISTS market_items ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "name TEXT NOT NULL,"
            "price_points INTEGER NOT NULL DEFAULT 0,"
            "stock INTEGER NOT NULL DEFAULT 0,"
            "meta_json TEXT"
            ")"
        )
        # market_orders
        c.execute(
            "CREATE TABLE IF NOT EXISTS market_orders ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER,"
            "item_id INTEGER NOT NULL,"
            "qty INTEGER NOT NULL DEFAULT 1,"
            "price_points INTEGER NOT NULL DEFAULT 0,"
            "total_points INTEGER NOT NULL DEFAULT 0,"
            "status TEXT DEFAULT 'pending',"
            "phone TEXT,"
            "address TEXT,"
            "meta_json TEXT,"
            "tracking_code TEXT,"
            "notes TEXT,"
            "member_code TEXT,"
            "updated_at TIMESTAMP,"
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_market_orders_user ON market_orders(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_market_orders_item ON market_orders(item_id)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_market_orders_tracking ON market_orders(tracking_code)")
        con.commit()
    finally:
        con.close()

# --- Tracking setup (idempotent) ---
def _ensure_market_tracking():
    con = get_db(); c = con.cursor()
    try:
        try:
            _ensure_market_tables()
        except Exception:
            pass

        cols = [r[1] for r in c.execute("PRAGMA table_info(market_orders)").fetchall()]
        if 'tracking_code' not in cols:
            c.execute("ALTER TABLE market_orders ADD COLUMN tracking_code TEXT")
        if 'notes' not in cols:
            c.execute("ALTER TABLE market_orders ADD COLUMN notes TEXT")
        if 'member_code' not in cols:
            c.execute("ALTER TABLE market_orders ADD COLUMN member_code TEXT")
        if 'updated_at' not in cols:
            c.execute("ALTER TABLE market_orders ADD COLUMN updated_at TIMESTAMP")

        # keep unique index
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_market_orders_tracking ON market_orders(tracking_code)")

        # trigger to auto fill tracking_code when NULL
        c.execute(
            "CREATE TRIGGER IF NOT EXISTS trg_market_orders_tracking "
            "AFTER INSERT ON market_orders "
            "FOR EACH ROW "
            "WHEN NEW.tracking_code IS NULL "
            "BEGIN "
            "  UPDATE market_orders "
            "    SET tracking_code = lower(hex(randomblob(8))) "
            "    WHERE id = NEW.id; "
            "END;"
        )
        con.commit()
    finally:
        con.close()

# --- Notify core (manual notification from admin) ---
def _admin_order_notify_core(order_id: int):
    if not _is_admin():
        return ("Not authorized", 403)
    con = get_db(); c = con.cursor()
    try:
        row = c.execute("SELECT * FROM market_orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            return ("Order not found", 404)
        ok = False
        try:
            order = {k: row[k] for k in getattr(row, "keys", lambda: [])()}
            if '_notify_buyer' in globals():
                ok = bool(_notify_buyer(order, reason="manual"))
        except Exception:
            pass
        try:
            flash("نۆتیفیکەیشن نێردرا." if ok else "هەوڵی ناردن شکستی هێنا.", "info" if ok else "error")
        except Exception:
            pass
        return redirect(url_for("admin_market") if "admin_market" in app.view_functions else "/admin/market")
    finally:
        con.close()

# --- Register /admin/market/order/<id>/notify ONCE (idempotent) ---
def _ensure_notify_registered():
    ep = "admin_market_order_notify"
    if ep not in app.view_functions:
        app.add_url_rule(
            "/admin/market/order/<int:order_id>/notify",
            endpoint=ep,
            view_func=lambda order_id: _admin_order_notify_core(order_id),
            methods=["POST"],
        )

# --- SAFETY GUARD: if someone calls _ensure_market_tracking() before this block, define a no-op fallback ---
if '_ensure_market_tracking' not in globals():
    # we just defined it above; this guard is for older copies—kept for safety
    def _ensure_market_tracking():
        try:
            _ensure_market_tables()
        except Exception:
            pass

# initialize once at import
try:
    _ensure_market_tables()
    _ensure_market_tracking()
    _ensure_notify_registered()
except Exception:
    pass

# =================== END MARKET DROP-IN PATCH ===================
# ========== NOTIFY ROUTE HARD-REGISTER (paste at VERY BOTTOM of app.py) ==========
# This guarantees the endpoint exists even if decorators/blueprints didn't add it.

from flask import redirect, url_for, flash

def _admin_order_notify_core(order_id):
    # Minimal safe fallback; if you already have a richer one, this will be ignored.
    try:
        if '_is_admin' in globals() and not _is_admin():
            return ("Not authorized", 403)
    except Exception:
        pass
    con = get_db(); c = con.cursor()
    try:
        row = c.execute("SELECT * FROM market_orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            return ("Order not found", 404)
        try:
            if '_notify_buyer' in globals():
                order = {k: row[k] for k in getattr(row, "keys", lambda: [])()}
                _notify_buyer(order, reason="manual")
                try:
                    flash("نۆتیفیکەیشن نێردرا.", "info")
                except Exception:
                    pass
        except Exception:
            pass
        return redirect(url_for("admin_market") if "admin_market" in app.view_functions else "/admin/market")
    finally:
        con.close()
def _force_register_admin_notify():
    ep = "admin_market_order_notify"
    # If endpoint missing, add a fresh rule
    if ep not in app.view_functions:
        app.add_url_rule(
            "/admin/market/order/<int:order_id>/notify",
            endpoint=ep,
            view_func=lambda order_id: _admin_order_notify_core(order_id),
            methods=["POST"],
        )

try:
    _force_register_admin_notify()
except Exception as _e:
    # last resort: make sure at least the view function exists for url_for to bind later
    app.view_functions["admin_market_order_notify"] = lambda order_id: _admin_order_notify_core(order_id)
# ========== END NOTIFY ROUTE HARD-REGISTER ==========

    try:
        c.execute(
            "CREATE TABLE IF NOT EXISTS market_items ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "name TEXT NOT NULL,"
            "price_points INTEGER NOT NULL DEFAULT 0,"
            "stock INTEGER NOT NULL DEFAULT 0,"
            "meta_json TEXT)"
        )
        c.execute(
            "CREATE TABLE IF NOT EXISTS market_orders ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER,"
            "item_id INTEGER NOT NULL,"
            "qty INTEGER NOT NULL DEFAULT 1,"
            "price_points INTEGER NOT NULL DEFAULT 0,"
            "total_points INTEGER NOT NULL DEFAULT 0,"
            "status TEXT DEFAULT 'pending',"
            "phone TEXT,"
            "address TEXT,"
            "meta_json TEXT,"
            "tracking_code TEXT,"
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_market_orders_user ON market_orders(user_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_market_orders_item ON market_orders(item_id)")
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_market_orders_tracking ON market_orders(tracking_code)")
        con.commit()
    finally:
        con.close()

if '_ensure_market_tracking' not in globals():
    def _ensure_market_tracking():
        """Add tracking_code + trigger; safe to call many times."""
        con = get_db(); c = con.cursor()
        try:
            # make sure base tables exist first
            try:
                _ensure_market_tables()
            except Exception:
                pass

            cols = [r[1] for r in c.execute("PRAGMA table_info(market_orders)").fetchall()]
            if 'tracking_code' not in cols:
                c.execute("ALTER TABLE market_orders ADD COLUMN tracking_code TEXT")

            # unique index
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_market_orders_tracking ON market_orders(tracking_code)")

            # trigger to auto-fill tracking_code if NULL
            c.execute(
                "CREATE TRIGGER IF NOT EXISTS trg_market_orders_tracking "
                "AFTER INSERT ON market_orders "
                "FOR EACH ROW "
                "WHEN NEW.tracking_code IS NULL "
                "BEGIN "
                "  UPDATE market_orders "
                "  SET tracking_code = lower(hex(randomblob(8))) "
                "  WHERE id = NEW.id; "
                "END;"
            )
            con.commit()
        finally:
            con.close()

# run once at import so the function exists and schema is ready
try:
    _ensure_market_tracking()
except Exception:
    pass
# ================== END HOTFIX ==================

# ================== APP RUN (clean) ==================
# Keep these two imports AT THE VERY END (before app.run) so patches can see `app` and `get_db`:
try:
   
    import market_tracking_hotfix  # market_patch_safe (hooks into __main__)
except Exception as _e:
    print("market_tracking_hotfix import warning:", _e)

if __name__ == "__main__":
    import os
    host  = os.getenv("HOST", "127.0.0.1")   # change to "0.0.0.0" to listen on all interfaces
    port  = int(os.getenv("PORT", "5000"))
    debug = (os.getenv("FLASK_DEBUG", "1") == "1")
    app.run(host=host, port=port, debug=debug)
