
# === market_patch (AUTO-REGISTER, SAFE, IDEMPOTENT) ===
# This file is intended to be imported at the END of app.py, once 'app' and 'get_db' exist.

import types
import os

# Try to grab 'app' and helpers from caller (your app.py global scope)
_g = globals()

# If we are imported from app.py, 'app' and 'get_db' should be there already.
app = _g.get("app")
get_db = _g.get("get_db")
session = _g.get("session")
flash = _g.get("flash")
url_for = _g.get("url_for")
redirect = _g.get("redirect")
request = _g.get("request")
render_template = _g.get("render_template")

if app is None or get_db is None:
    raise RuntimeError("market_patch must be imported after 'app' and 'get_db' are defined")

# ---------- Helpers ----------
def _safe_is_admin():
    try:
        # Respect your existing role system if present
        if "_has_role" in _g:
            try:
                if _g["_has_role"]("admin") or _g["_has_role"]("superadmin"):
                    return True
            except Exception:
                pass
        return bool(session.get("is_admin") or session.get("admin"))
    except Exception:
        return False

# ---------- Tables (idempotent) ----------
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
            "is_active INTEGER NOT NULL DEFAULT 1,"
            "meta_json TEXT,"
            "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
        # market_orders
        c.execute(
            "CREATE TABLE IF NOT EXISTS market_orders ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "user_id INTEGER,"
            "item_id INTEGER NOT NULL,"
            "qty INTEGER NOT NULL DEFAULT 1,"
            "points_total INTEGER,"
            "status TEXT DEFAULT 'pending',"
            "phone TEXT,"
            "address TEXT,"
            "notes TEXT,"
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

def _ensure_market_tracking():
    con = get_db(); c = con.cursor()
    try:
        try:
            _ensure_market_tables()
        except Exception:
            pass
        # ensure columns exist
        cols = [r[1] for r in c.execute("PRAGMA table_info(market_orders)").fetchall()]
        if "tracking_code" not in cols:
            c.execute("ALTER TABLE market_orders ADD COLUMN tracking_code TEXT")
        if "notes" not in cols:
            c.execute("ALTER TABLE market_orders ADD COLUMN notes TEXT")
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

# If your app already has _ensure_market_tracking, don't override it.
if "_ensure_market_tracking" not in _g:
    _g["_ensure_market_tracking"] = _ensure_market_tracking

# ---------- Notify core ----------
def _admin_order_notify_core(order_id: int):
    if not _safe_is_admin():
        return ("Not authorized", 403)
    con = get_db(); c = con.cursor()
    try:
        row = c.execute("SELECT * FROM market_orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            return ("Order not found", 404)
        # Build order dict best-effort
        order = {}
        try:
            if hasattr(row, "keys"):
                order = {k: row[k] for k in row.keys()}
        except Exception:
            pass
        # Call your existing notifier if present
        ok = False
        try:
            if "_notify_buyer" in _g:
                ok = bool(_g["_notify_buyer"](order, reason="manual"))
        except Exception:
            ok = False
        try:
            flash("نۆتیفیکەیشن نێردرا." if ok else "هەوڵی ناردن شکستی هێنا.", "info" if ok else "error")
        except Exception:
            pass
        return redirect(url_for("admin_market") if "admin_market" in app.view_functions else "/admin/market")
    finally:
        con.close()

# If your app already defines _admin_order_notify_core, keep it.
if "_admin_order_notify_core" not in _g:
    _g["_admin_order_notify_core"] = _admin_order_notify_core

# ---------- Register /__routes once ----------
def __routes():
    try:
        rules = sorted([f"{r.rule} -> {r.endpoint}" for r in app.url_map.iter_rules()])
        return "<pre>" + "\\n".join(rules) + "</pre>"
    except Exception as e:
        return f"error: {e}", 500

if "__routes" not in app.view_functions:
    app.add_url_rule("/__routes", endpoint="__routes", view_func=__routes, methods=["GET"])

# ---------- Register notify endpoint ONCE ----------
ep = "admin_market_order_notify"
if ep not in app.view_functions:
    app.add_url_rule(
        "/admin/market/order/<int:order_id>/notify",
        endpoint=ep,
        view_func=lambda order_id: _g["_admin_order_notify_core"](order_id),
        methods=["POST"],
    )

# Ensure schema early at import (safe)
try:
    _ensure_market_tables()
    _ensure_market_tracking()
except Exception:
    pass

# === end of market_patch ===
