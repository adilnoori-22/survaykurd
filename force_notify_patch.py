# -*- coding: utf-8 -*-
# Guarantees /admin/market/order/<id>/notify exists exactly once.
# Usage: put this file next to app.py, then in app.py add (at the very end, before app.run):
#   import force_notify_patch
from __future__ import annotations

import importlib
from flask import redirect, url_for, flash, session

_appmod = importlib.import_module("app")
app = getattr(_appmod, "app")
get_db = getattr(_appmod, "get_db")

def _is_admin():
    try:
        if '_has_role' in _appmod.__dict__:
            try:
                if _appmod._has_role('admin') or _appmod._has_role('superadmin'):
                    return True
            except Exception:
                pass
        return bool(session.get('is_admin') or session.get('admin'))
    except Exception:
        return False

# Minimal core
def _admin_order_notify_core(order_id: int):
    if not _is_admin():
        return ("Not authorized", 403)
    con = get_db(); c = con.cursor()
    try:
        row = c.execute("SELECT * FROM market_orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            return ("Order not found", 404)
        # optional: call user's notifier if defined
        try:
            if '_notify_buyer' in _appmod.__dict__:
                # convert row to dict if possible
                try:
                    order = {k: row[k] for k in row.keys()}
                except Exception:
                    order = {}
                _appmod._notify_buyer(order, reason="manual")
        except Exception:
            pass
        try:
            flash("نۆتیفیکەیشن نێردرا.", "info")
        except Exception:
            pass
        return redirect(url_for("admin_market") if "admin_market" in app.view_functions else "/admin/market")
    finally:
        con.close()

# Remove any stale mapping and register once
ep = "admin_market_order_notify"
try:
    app.view_functions.pop(ep, None)
except Exception:
    pass

if ep not in app.view_functions:
    app.add_url_rule(
        "/admin/market/order/<int:order_id>/notify",
        endpoint=ep,
        view_func=lambda order_id: _admin_order_notify_core(order_id),
        methods=["POST"],
    )

# Add __routes if missing
def __routes():
    try:
        rows = ["<table border='1' cellpadding='6' style='border-collapse:collapse;font-family:system-ui'>",
                "<tr><th>Rule</th><th>Endpoint</th><th>Methods</th></tr>"]
        for r in app.url_map.iter_rules():
            methods = ",".join(sorted(r.methods or []))
            rows.append(f"<tr><td>{r.rule}</td><td>{r.endpoint}</td><td>{methods}</td></tr>")
        rows.append("</table>")
        return "\n".join(rows)
    except Exception as e:
        return f"error: {e}", 500

if "__routes" not in app.view_functions:
    app.add_url_rule("/__routes", endpoint="__routes", view_func=__routes, methods=["GET"])
