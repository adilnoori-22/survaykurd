# ==== ADMIN ADS CONFIG (Global Defaults + Per-Game Config + CREDIT LOGGING) ====
def _install_ads_config(app, store_path='ads_config.json', credit_store='ads_impressions.json', defaults_path='ads_defaults.json'):
    import json, os, time
    from flask import request, jsonify, render_template_string, redirect, url_for, session, flash
    from ads_helper import credit_points_for_ad

    store_path   = os.path.abspath(store_path)
    credit_store = os.path.abspath(credit_store)
    defaults_path= os.path.abspath(defaults_path)

    # ---------- IO ----------
    def _load(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(data, path):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True

    def _append_credit(entry):
        rows = []
        try:
            with open(credit_store, 'r', encoding='utf-8') as f:
                rows = json.load(f)
                if not isinstance(rows, list):
                    rows = []
        except Exception:
            rows = []
        rows.append(entry)
        with open(credit_store, 'w', encoding='utf-8') as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        return True

    # ---------- Defaults ----------
    DEFAULTS = {
        'start': True,
        'level_end': False,
        'mid_level': False,
        'every_n_levels': 1,
        'cooldown_sec': 0,
        'max_per_session': 0,
        'probability': 100,
        'start_delay_ms': 0,
        'ad_unit_id': '',
        'platform_desktop': True,
        'platform_mobile': True,
        'room_allow': [],
        'room_deny': [],
        'daily_cap': 0,
        'schedule_from': '',
        'schedule_to': '',
        'skip_for_admins': False,
        'skip_click_games': False,
        'variants': []  # [{name, weight, ad_unit_id, html}]
    }

    def _normalize(d):
        out = DEFAULTS.copy()
        d = d or {}
        for k in DEFAULTS:
            if k in d:
                out[k] = d[k]

        out['start']             = bool(out['start'])
        out['level_end']         = bool(out['level_end'])
        out['mid_level']         = bool(out['mid_level'])
        out['every_n_levels']    = max(1, int(out.get('every_n_levels') or 1))
        out['cooldown_sec']      = max(0, int(out.get('cooldown_sec') or 0))
        out['max_per_session']   = max(0, int(out.get('max_per_session') or 0))
        out['probability']       = max(0, min(100, int(out.get('probability') or 100)))
        out['start_delay_ms']    = max(0, int(out.get('start_delay_ms') or 0))
        out['ad_unit_id']        = str(out.get('ad_unit_id') or '')
        out['platform_desktop']  = bool(out['platform_desktop'])
        out['platform_mobile']   = bool(out['platform_mobile'])
        out['daily_cap']         = max(0, int(out.get('daily_cap') or 0))
        out['schedule_from']     = str(out.get('schedule_from') or '')
        out['schedule_to']       = str(out.get('schedule_to') or '')
        out['skip_for_admins']   = bool(out.get('skip_for_admins'))
        out['skip_click_games']  = bool(out.get('skip_click_games'))

        def norm_rooms(val):
            if val is None:
                return []
            if isinstance(val, list):
                return [str(x).strip() for x in val if str(x).strip()]
            if isinstance(val, str):
                return [x.strip() for x in val.split(',') if x.strip()]
            return []
        out['room_allow'] = norm_rooms(d.get('room_allow'))
        out['room_deny']  = norm_rooms(d.get('room_deny'))

        vnorm = []
        for item in (d.get('variants') or []):
            try:
                name   = str(item.get('name') or '').strip()
                weight = int(item.get('weight') or 0)
                unit   = str(item.get('ad_unit_id') or '')
                html   = str(item.get('html') or '')
                if name and weight > 0:
                    vnorm.append({'name': name, 'weight': weight, 'ad_unit_id': unit, 'html': html})
            except Exception:
                continue
        out['variants'] = vnorm
        return out

    def _merge_with_defaults(per_game):
        # file defaults -> hard defaults -> per_game
        global_def = _load(defaults_path) or {}
        base = DEFAULTS.copy()
        if isinstance(global_def, dict):
            for k, v in global_def.items():
                if k in base:
                    base[k] = v
        for k, v in (per_game or {}).items():
            base[k] = v
        return _normalize(base)

    # ---------- API ----------
    @app.get('/api/ads/config')
    def api_ads_config():
        game_id = request.args.get('game_id', type=int)
        if not game_id:
            return jsonify({'ok': False, 'error': 'game_id required'}), 400
        data = _load(store_path)
        conf = _merge_with_defaults(data.get(str(game_id), {}))
        # is_admin flag (for skip rules)
        is_admin = False
        try:
            from flask_login import current_user
            is_admin = bool(getattr(current_user, 'is_admin', False))
        except Exception:
            is_admin = bool(session.get('is_admin'))
        conf['_is_admin'] = is_admin
        return jsonify({'ok': True, 'config': conf})

    @app.post('/api/ads/credit')
    def api_ads_credit():
        payload = {}
        try:
            payload = request.get_json(force=True, silent=False) or {}
        except Exception:
            try:
                payload = request.get_json(silent=True) or {}
            except Exception:
                payload = {}

        game_id  = int(payload.get('game_id') or 0)
        ad_id    = str(payload.get('ad_id') or '')
        variant  = str(payload.get('variant') or '')
        room     = str(payload.get('room') or '')
        platform = str(payload.get('platform') or '')
        event    = str(payload.get('event') or 'view')
        meta     = payload.get('meta') or {}

        if not game_id:
            return jsonify({'ok': False, 'error': 'game_id required'}), 400

        entry = {
            'ts': int(time.time()),
            'game_id': game_id,
            'ad_id': ad_id,
            'variant': variant,
            'room': room,
            'platform': platform,
            'event': event,
            'meta': meta
        }
        _append_credit(entry)
        # Credit wallet points for this ad view
        try:
            uid = session.get('user_id') or session.get('uid')
            if uid:
                credit_points_for_ad(int(uid), int(game_id), int(ad_id) if str(ad_id).isdigit() else 0, default_points=2)
        except Exception:
            pass
        return jsonify({'ok': True, 'points': int(locals().get('___last_pts', 0))})

    # ---------- Admin: Global Defaults ----------
    @app.route('/admin/ads/defaults', methods=['GET', 'POST'])
    def admin_ads_defaults():
        if request.method == 'POST':
            conf = {
                'start': bool(request.form.get('start')),
                'level_end': bool(request.form.get('level_end')),
                'mid_level': bool(request.form.get('mid_level')),
                'every_n_levels': request.form.get('every_n_levels') or 1,
                'cooldown_sec': request.form.get('cooldown_sec') or 0,
                'max_per_session': request.form.get('max_per_session') or 0,
                'probability': request.form.get('probability') or 100,
                'start_delay_ms': request.form.get('start_delay_ms') or 0,
                'ad_unit_id': request.form.get('ad_unit_id') or '',
                'platform_desktop': bool(request.form.get('platform_desktop')),
                'platform_mobile': bool(request.form.get('platform_mobile')),
                'room_allow': (request.form.get('room_allow') or ''),
                'room_deny': (request.form.get('room_deny') or ''),
                'daily_cap': request.form.get('daily_cap') or 0,
                'schedule_from': request.form.get('schedule_from') or '',
                'schedule_to': request.form.get('schedule_to') or '',
                'skip_for_admins': bool(request.form.get('skip_for_admins')),
                'skip_click_games': bool(request.form.get('skip_click_games')),
                'variants': []
            }
            names  = request.form.getlist('v_name')
            weights= request.form.getlist('v_weight')
            units  = request.form.getlist('v_unit')
            htmls  = request.form.getlist('v_html')
            for i in range(len(names)):
                n = (names[i] or '').strip()
                try:
                    w = int(weights[i] or 0)
                except Exception:
                    w = 0
                u = (units[i] or '').strip()
                h = (htmls[i] or '').strip() if i < len(htmls) else ''
                if n and w > 0:
                    conf['variants'].append({'name': n, 'weight': w, 'ad_unit_id': u, 'html': h})

            _save(_normalize(conf), defaults_path)
            try:
                flash('Saved.', 'success')
            except Exception:
                pass
            return redirect(url_for('admin_ads_defaults'))

        conf = _merge_with_defaults({})
        # NOTE: no list/dict literals inside {% ... %}; only filters/strings are used.
        html = r"""
        {% extends "base.html" %}
        {% block title %}Ad Defaults{% endblock %}
        {% block content %}
        <h2>Ad Defaults (Site-wide)</h2>
        <form method="post" class="card" style="display:flex;flex-direction:column;gap:1rem;max-width:1000px">
          <fieldset class="card">
            <legend>Basics</legend>
            <div style="display:grid;grid-template-columns:repeat(3, minmax(200px,1fr));gap:.6rem">
              <label><input type="checkbox" name="start" {% if conf.start %}checked{% endif %}> At game start</label>
              <label><input type="checkbox" name="level_end" {% if conf.level_end %}checked{% endif %}> At level end</label>
              <label><input type="checkbox" name="mid_level" {% if conf.mid_level %}checked{% endif %}> Mid-level</label>

              <label>Every N levels <input type="number" min="1" name="every_n_levels" value="{{ conf.every_n_levels }}" class="input" style="width:120px"></label>
              <label>Cooldown (sec) <input type="number" min="0" name="cooldown_sec" value="{{ conf.cooldown_sec }}" class="input" style="width:120px"></label>
              <label>Max per session <input type="number" min="0" name="max_per_session" value="{{ conf.max_per_session }}" class="input" style="width:120px"></label>

              <label>Probability % <input type="number" min="0" max="100" name="probability" value="{{ conf.probability }}" class="input" style="width:120px"></label>
              <label>Start delay (ms) <input type="number" min="0" name="start_delay_ms" value="{{ conf.start_delay_ms }}" class="input" style="width:120px"></label>
              <label>Ad Unit ID <input type="text" name="ad_unit_id" value="{{ conf.ad_unit_id }}" class="input" placeholder="unit-default"></label>
            </div>
          </fieldset>

          <fieldset class="card">
            <legend>Targeting</legend>
            <div style="display:grid;grid-template-columns:repeat(3, minmax(220px,1fr));gap:.6rem">
              <label><input type="checkbox" name="platform_desktop" {% if conf.platform_desktop %}checked{% endif %}> Desktop</label>
              <label><input type="checkbox" name="platform_mobile" {% if conf.platform_mobile %}checked{% endif %}> Mobile</label>
              <label><input type="checkbox" name="skip_for_admins" {% if conf.skip_for_admins %}checked{% endif %}> Skip for admins</label>
              <label><input type="checkbox" name="skip_click_games" {% if conf.skip_click_games %}checked{% endif %}> Skip click-games</label>

              <div>
                <div class="muted" style="margin-bottom:.2rem">Allow rooms</div>
                <input name="room_allow" class="input" placeholder="public, vip, ..." value="{{ conf.room_allow|join(', ') }}">
              </div>
              <div>
                <div class="muted" style="margin-bottom:.2rem">Deny rooms</div>
                <input name="room_deny" class="input" placeholder="mod, staff, ..." value="{{ conf.room_deny|join(', ') }}">
              </div>

              <div>
                <div class="muted">Daily cap</div>
                <input type="number" min="0" name="daily_cap" value="{{ conf.daily_cap }}" class="input" style="width:140px">
                <div class="muted" style="margin-top:.6rem">Working hours</div>
                <div class="row" style="gap:.4rem">
                  <input type="time" name="schedule_from" value="{{ conf.schedule_from }}" class="input" style="width:140px">
                  <input type="time" name="schedule_to" value="{{ conf.schedule_to }}" class="input" style="width:140px">
                </div>
              </div>
            </div>
          </fieldset>

          <fieldset class="card">
            <legend>A/B Variants</legend>
            <div id="variants" style="display:flex;flex-direction:column;gap:.6rem">
              {% for v in conf.variants %}
              <div class="row" style="gap:.6rem;align-items:center;flex-wrap:wrap">
                <input name="v_name"  value="{{ v.name }}"  placeholder="Name (e.g. A)" class="input" style="width:140px">
                <input name="v_weight" value="{{ v.weight }}" type="number" min="1" placeholder="Weight" class="input" style="width:120px">
                <input name="v_unit"  value="{{ v.ad_unit_id }}" placeholder="Ad Unit ID" class="input" style="flex:1;min-width:240px">
                <button type="button" class="btn small danger" onclick="this.parentNode.remove()">Delete</button>
                <textarea name="v_html" placeholder="Optional HTML for this variant" class="input" style="width:100%;height:90px">{{ v.html }}</textarea>
              </div>
              {% endfor %}
            </div>
            <button type="button" class="btn small" onclick="addVariant()">+ Add Variant</button>
            <script>
            function addVariant(){
              var d = document.createElement('div');
              d.className = 'row';
              d.style.cssText = 'gap:.6rem;align-items:center;flex-wrap:wrap';
              d.innerHTML = '<input name="v_name" placeholder="Name (e.g. B)" class="input" style="width:140px">'
                          + '<input name="v_weight" type="number" min="1" value="50" placeholder="Weight" class="input" style="width:120px">'
                          + '<input name="v_unit" placeholder="Ad Unit ID" class="input" style="flex:1;min-width:240px">'
                          + '<button type="button" class="btn small danger" onclick="this.parentNode.remove()">Delete</button>'
                          + '<textarea name="v_html" placeholder="Optional HTML for this variant" class="input" style="width:100%;height:90px;margin-top:.4rem"></textarea>';
              document.getElementById('variants').appendChild(d);
            }
            </script>
          </fieldset>

          <div style="display:flex;gap:.6rem;align-items:center">
            <button class="btn primary">Save</button>
            <a class="btn secondary" href="{{ url_for('admin_games') }}">Back</a>
          </div>
        </form>
        {% endblock %}
        """
        return render_template_string(html, conf=conf)

    # ---------- Admin: Per-Game ----------
    @app.route('/admin/games/<int:game_id>/ads-config', methods=['GET', 'POST'])
    def admin_game_ads_config(game_id):
        data = _load(store_path)
        if request.method == 'POST':
            conf = {
                'start': bool(request.form.get('start')),
                'level_end': bool(request.form.get('level_end')),
                'mid_level': bool(request.form.get('mid_level')),
                'every_n_levels': request.form.get('every_n_levels') or 1,
                'cooldown_sec': request.form.get('cooldown_sec') or 0,
                'max_per_session': request.form.get('max_per_session') or 0,
                'probability': request.form.get('probability') or 100,
                'start_delay_ms': request.form.get('start_delay_ms') or 0,
                'ad_unit_id': request.form.get('ad_unit_id') or '',
                'platform_desktop': bool(request.form.get('platform_desktop')),
                'platform_mobile': bool(request.form.get('platform_mobile')),
                'room_allow': (request.form.get('room_allow') or ''),
                'room_deny': (request.form.get('room_deny') or ''),
                'daily_cap': request.form.get('daily_cap') or 0,
                'schedule_from': request.form.get('schedule_from') or '',
                'schedule_to': request.form.get('schedule_to') or '',
                'skip_for_admins': bool(request.form.get('skip_for_admins')),
                'skip_click_games': bool(request.form.get('skip_click_games')),
                'variants': []
            }
            names  = request.form.getlist('v_name')
            weights= request.form.getlist('v_weight')
            units  = request.form.getlist('v_unit')
            htmls  = request.form.getlist('v_html')
            for i in range(len(names)):
                n = (names[i] or '').strip()
                try:
                    w = int(weights[i] or 0)
                except Exception:
                    w = 0
                u = (units[i] or '').strip()
                h = (htmls[i] or '').strip() if i < len(htmls) else ''
                if n and w > 0:
                    conf['variants'].append({'name': n, 'weight': w, 'ad_unit_id': u, 'html': h})

            data[str(game_id)] = _normalize(conf)
            _save(data, store_path)
            try:
                flash('Saved.', 'success')
            except Exception:
                pass
            return redirect(url_for('admin_game_ads_config', game_id=game_id))

        conf = _merge_with_defaults(_load(store_path).get(str(game_id), {}))
        html = r"""
        {% extends "base.html" %}
        {% block title %}Ad Config - Game #{{ game_id }}{% endblock %}
        {% block content %}
        <h2>Ad Config for Game #{{ game_id }}</h2>
        <div class="row" style="gap:.5rem;margin-bottom:.6rem">
          <a class="btn small" href="{{ url_for('admin_ads_defaults') }}">Defaults</a>
          <a class="btn small" href="{{ url_for('admin_game_ads_analytics', game_id=game_id) }}">Analytics</a>
          <a class="btn small" target="_blank" href="{{ url_for('games_play', game_id=game_id) }}?adtest=1">Test (adtest)</a>
        </div>

        <form method="post" class="card" style="display:flex;flex-direction:column;gap:1rem;max-width:1000px">
          <fieldset class="card">
            <legend>Basics</legend>
            <div style="display:grid;grid-template-columns:repeat(3, minmax(200px,1fr));gap:.6rem">
              <label><input type="checkbox" name="start" {% if conf.start %}checked{% endif %}> At game start</label>
              <label><input type="checkbox" name="level_end" {% if conf.level_end %}checked{% endif %}> At level end</label>
              <label><input type="checkbox" name="mid_level" {% if conf.mid_level %}checked{% endif %}> Mid-level</label>

              <label>Every N levels <input type="number" min="1" name="every_n_levels" value="{{ conf.every_n_levels }}" class="input" style="width:120px"></label>
              <label>Cooldown (sec) <input type="number" min="0" name="cooldown_sec" value="{{ conf.cooldown_sec }}" class="input" style="width:120px"></label>
              <label>Max per session <input type="number" min="0" name="max_per_session" value="{{ conf.max_per_session }}" class="input" style="width:120px"></label>

              <label>Probability % <input type="number" min="0" max="100" name="probability" value="{{ conf.probability }}" class="input" style="width:120px"></label>
              <label>Start delay (ms) <input type="number" min="0" name="start_delay_ms" value="{{ conf.start_delay_ms }}" class="input" style="width:120px"></label>
              <label>Ad Unit ID <input type="text" name="ad_unit_id" value="{{ conf.ad_unit_id }}" class="input" placeholder="unit-default"></label>
            </div>
          </fieldset>

          <fieldset class="card">
            <legend>Targeting</legend>
            <div style="display:grid;grid-template-columns:repeat(3, minmax(220px,1fr));gap:.6rem">
              <label><input type="checkbox" name="platform_desktop" {% if conf.platform_desktop %}checked{% endif %}> Desktop</label>
              <label><input type="checkbox" name="platform_mobile" {% if conf.platform_mobile %}checked{% endif %}> Mobile</label>
              <label><input type="checkbox" name="skip_for_admins" {% if conf.skip_for_admins %}checked{% endif %}> Skip for admins</label>
              <label><input type="checkbox" name="skip_click_games" {% if conf.skip_click_games %}checked{% endif %}> Skip click-games</label>

              <div>
                <div class="muted" style="margin-bottom:.2rem">Allow rooms</div>
                <input name="room_allow" class="input" placeholder="public, vip, ..." value="{{ conf.room_allow|join(', ') }}">
              </div>
              <div>
                <div class="muted" style="margin-bottom:.2rem">Deny rooms</div>
                <input name="room_deny" class="input" placeholder="mod, staff, ..." value="{{ conf.room_deny|join(', ') }}">
              </div>

              <div>
                <div class="muted">Daily cap</div>
                <input type="number" min="0" name="daily_cap" value="{{ conf.daily_cap }}" class="input" style="width:140px">
                <div class="muted" style="margin-top:.6rem">Working hours</div>
                <div class="row" style="gap:.4rem">
                  <input type="time" name="schedule_from" value="{{ conf.schedule_from }}" class="input" style="width:140px">
                  <input type="time" name="schedule_to" value="{{ conf.schedule_to }}" class="input" style="width:140px">
                </div>
              </div>
            </div>
          </fieldset>

          <fieldset class="card">
            <legend>A/B Variants</legend>
            <div id="variants" style="display:flex;flex-direction:column;gap:.6rem">
              {% for v in conf.variants %}
              <div class="row" style="gap:.6rem;align-items:center;flex-wrap:wrap">
                <input name="v_name"  value="{{ v.name }}"  placeholder="Name (e.g. A)" class="input" style="width:140px">
                <input name="v_weight" value="{{ v.weight }}" type="number" min="1" placeholder="Weight" class="input" style="width:120px">
                <input name="v_unit"  value="{{ v.ad_unit_id }}" placeholder="Ad Unit ID" class="input" style="flex:1;min-width:240px">
                <button type="button" class="btn small danger" onclick="this.parentNode.remove()">Delete</button>
                <textarea name="v_html" placeholder="Optional HTML for this variant" class="input" style="width:100%;height:90px">{{ v.html }}</textarea>
              </div>
              {% endfor %}
            </div>
            <button type="button" class="btn small" onclick="addVariant()">+ Add Variant</button>
            <script>
            function addVariant(){
              var d = document.createElement('div');
              d.className = 'row';
              d.style.cssText = 'gap:.6rem;align-items:center;flex-wrap:wrap';
              d.innerHTML = '<input name="v_name" placeholder="Name (e.g. B)" class="input" style="width:140px">'
                          + '<input name="v_weight" type="number" min="1" value="50" placeholder="Weight" class="input" style="width:120px">'
                          + '<input name="v_unit" placeholder="Ad Unit ID" class="input" style="flex:1;min-width:240px">'
                          + '<button type="button" class="btn small danger" onclick="this.parentNode.remove()">Delete</button>'
                          + '<textarea name="v_html" placeholder="Optional HTML for this variant" class="input" style="width:100%;height:90px;margin-top:.4rem"></textarea>';
              document.getElementById('variants').appendChild(d);
            }
            </script>
          </fieldset>

          <div style="display:flex;gap:.6rem;align-items:center">
            <button class="btn primary">Save</button>
            <a class="btn secondary" href="{{ url_for('admin_games_edit', game_id=game_id) }}">Back</a>
            <a class="btn" target="_blank" href="{{ url_for('games_play', game_id=game_id) }}?adtest=1">Test</a>
            <a class="btn" href="{{ url_for('admin_game_ads_analytics', game_id=game_id) }}">Analytics</a>
          </div>
        </form>
        {% endblock %}
        """
        return render_template_string(html, game_id=game_id, conf=conf)
# ==== END CONFIG ====




