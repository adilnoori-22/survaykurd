# -*- coding: utf-8 -*-
# Runtime-safe hotfix: use the *current* running module (__main__) instead of importing "app".
# Usage: put this file next to app.py, then at the VERY END of app.py (before app.run if present):
#     import market_tracking_hotfix_runtime  # keep
from __future__ import annotations

import sys

_appmod = sys.modules.get("__main__")
if _appmod is None:
    raise RuntimeError("Cannot locate running app module (__main__). Make sure you import this at the end of app.py.")

app = getattr(_appmod, "app")
get_db = getattr(_appmod, "get_db")

# ---------- Safe schema helpers (define if missing) ----------
if "_ensure_market_tables" not in _appmod.__dict__:
    def _ensure_market_tables():
        con = get_db(); c = con.cursor()
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
    _appmod._ensure_market_tables = _ensure_market_tables
else:
    _ensure_market_tables = _appmod._ensure_market_tables

if "_ensure_market_tracking" not in _appmod.__dict__:
    def _ensure_market_tracking():
        con = get_db(); c = con.cursor()
        try:
            try:
                _ensure_market_tables()
            except Exception:
                pass
            cols = [r[1] for r in c.execute("PRAGMA table_info(market_orders)").fetchall()]
            if "tracking_code" not in cols:
                c.execute("ALTER TABLE market_orders ADD COLUMN tracking_code TEXT")
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_market_orders_tracking ON market_orders(tracking_code)")
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
    _appmod._ensure_market_tracking = _ensure_market_tracking
else:
    _ensure_market_tracking = _appmod._ensure_market_tracking

# ---------- Wrap /market view to call ensure before executing ----------
_market_ep = "market"
if _market_ep in app.view_functions:
    _orig_market_view = app.view_functions[_market_ep]

    def _wrapped_market_view(*args, **kwargs):
        try:
            _ensure_market_tracking()
        except Exception:
            try:
                _ensure_market_tables()
            except Exception:
                pass
        return _orig_market_view(*args, **kwargs)

    app.view_functions[_market_ep] = _wrapped_market_view
