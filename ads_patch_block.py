# -*- coding: utf-8 -*-
from flask import request, jsonify, session, redirect, url_for, render_template
from ads_helper import (
    ads_migrate, ads_admin_list, ads_admin_create, ads_admin_toggle, ads_admin_delete,
    ad_get_start, ad_pick, credit_points_for_ad
)

def register_ads_routes(app):
    """Register ad admin + serve routes, guarding against duplicate endpoints.
    We SKIP registering `/api/ads/credit` if another module already provided it
    (e.g., app_ads_config_patch.py), to prevent `AssertionError: overwriting endpoint`.
    """

    # ---- Admin: per-game ads CRUD ----
    def admin_game_ads(game_id):
        # TODO: @admin_required in your app
        if request.method == 'POST':
            title      = (request.form.get('title') or '').strip()
            image_url  = (request.form.get('image_url') or '').strip()
            click_url  = (request.form.get('click_url') or '').strip()
            html       = (request.form.get('html') or '').strip()
            reward_pts = int(request.form.get('reward_points') or 0)
            active     = 1 if (request.form.get('active') == 'on') else 0
            ads_admin_create(game_id, title, image_url, click_url, html, reward_pts, active)
        rows = ads_admin_list(game_id)
        return render_template('admin/game_ads.html', game_id=game_id, rows=rows)

    # ---- API: serve next ad ----
    def api_ads_serve():
        try:
            game_id   = int(request.args.get('game_id') or request.form.get('game_id') or 0)
        except Exception:
            return jsonify(ok=False, error='game_id required'), 400
        room      = (request.args.get('room') or request.form.get('room') or '').strip()
        platform  = (request.args.get('platform') or request.form.get('platform') or '').strip()
        ad = ad_pick(game_id, room=room, platform=platform)
        return jsonify(ok=True, ad=ad)

    # ---- API: credit (only if not already provided elsewhere) ----
    def api_ads_credit():
        data = request.get_json(silent=True) or {}
        try:
            gid = int(data.get('game_id'))
            ad_id = int(data.get('ad_id'))
        except Exception:
            return jsonify(ok=False, error='bad payload'), 400
        user_id = session.get('user_id') or session.get('uid') or 0
        if not user_id:
            return jsonify(ok=False, error='not_authenticated'), 401
        pts = credit_points_for_ad(int(user_id), gid, ad_id, default_points=2)
        return jsonify(ok=True, points=pts)

    # ---- Portal redirect (optional convenience) ----
    def __portal_game_redirect(game_id):
        return redirect(url_for('games_play', game_id=game_id))

    # Helper: safe add
    def _add(rule, endpoint, view_func, methods):
        if endpoint in app.view_functions:
            return
        app.add_url_rule(rule, endpoint=endpoint, view_func=view_func, methods=methods)

    # Register guarded
    _add('/admin/games/<int:game_id>/ads', 'admin_game_ads', admin_game_ads, ['GET','POST'])
    _add('/api/ads/serve', 'api_ads_serve', api_ads_serve, ['GET'])

    # Only add credit if not already present (to avoid conflict with app_ads_config_patch.api_ads_credit)
    if 'api_ads_credit' not in app.view_functions:
        _add('/api/ads/credit', 'api_ads_credit', api_ads_credit, ['POST'])

    _add('/portal/game/<int:game_id>', '__portal_game_redirect', __portal_game_redirect, ['GET'])
