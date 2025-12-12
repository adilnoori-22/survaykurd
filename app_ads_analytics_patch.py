# ==== ADMIN ADS ANALYTICS (reads ads_impressions.json) ====
def _install_ads_analytics(app, credit_store='ads_impressions.json'):
    import json, os, time
    from collections import Counter
    from flask import request, render_template_string, redirect, url_for

    credit_store = os.path.abspath(credit_store)

    def _load():
        try:
            with open(credit_store, 'r', encoding='utf-8') as f:
                rows = json.load(f)
                if not isinstance(rows, list):
                    return []
                return rows
        except Exception:
            return []

    def _filter(rows, game_id=None, date_from=None, date_to=None, variant=None, room=None, platform=None):
        out = []
        for r in rows:
            if game_id and int(r.get('game_id') or 0) != int(game_id):
                continue
            ts = int(r.get('ts') or 0)
            if date_from and ts < date_from:
                continue
            if date_to and ts >= date_to:
                continue
            if variant and (r.get('variant') or '') != variant:
                continue
            if room and (r.get('room') or '') != room:
                continue
            if platform and (r.get('platform') or '') != platform:
                continue
            out.append(r)
        return out

    def _human_date(ts):
        try:
            return time.strftime('%Y-%m-%d %H:%M', time.localtime(ts))
        except Exception:
            return str(ts)

    @app.route('/admin/ads/analytics')
    def admin_ads_analytics():
        rows = _load()
        game_id = request.args.get('game_id', type=int)
        variant = request.args.get('variant') or ''
        room = request.args.get('room') or ''
        platform = request.args.get('platform') or ''
        df = request.args.get('from') or ''
        dt = request.args.get('to') or ''

        def to_ts(d):
            if not d: return None
            try:
                return int(time.mktime(time.strptime(d + ' 00:00:00', '%Y-%m-%d %H:%M:%S')))
            except Exception:
                return None

        date_from = to_ts(df)
        date_to = to_ts(dt)
        filt = _filter(rows, game_id, date_from, date_to, variant or None, room or None, platform or None)

        by_day = Counter(time.strftime('%Y-%m-%d', time.localtime(r.get('ts', 0))) for r in filt)
        by_game = Counter(int(r.get('game_id') or 0) for r in filt)
        by_variant = Counter((r.get('variant') or '') for r in filt)
        by_room = Counter((r.get('room') or '') for r in filt)
        by_platform = Counter((r.get('platform') or '') for r in filt)

        
        rows_head = sorted(filt, key=lambda r: int(r.get('ts',0)), reverse=True)[:100]

        html = r"""
{% extends "base.html" %}
{% block title %}ئەنالیتیکسی ڕیکلام{% endblock %}
{% block content %}
<h2>ئەنالیتیکسی ڕیکلام</h2>

<form class="card" method="get" style="display:flex;gap:.5rem;flex-wrap:wrap;align-items:flex-end">
  <label>Game ID <input class="input" type="number" name="game_id" value="{{ request.args.get('game_id','') }}" style="width:120px"></label>
  <label>Variant <input class="input" name="variant" value="{{ request.args.get('variant','') }}" style="width:120px"></label>
  <label>Room <input class="input" name="room" value="{{ request.args.get('room','') }}" style="width:120px"></label>
  <label>Platform
    <select class="input" name="platform" style="width:140px">
      {% set p = request.args.get('platform','') %}
      <option value="" {% if not p %}selected{% endif %}>Any</option>
      <option value="desktop" {% if p=='desktop' %}selected{% endif %}>Desktop</option>
      <option value="mobile" {% if p=='mobile' %}selected{% endif %}>Mobile</option>
    </select>
  </label>
  <label>From <input class="input" type="date" name="from" value="{{ request.args.get('from','') }}"></label>
  <label>To <input class="input" type="date" name="to" value="{{ request.args.get('to','') }}"></label>
  <button class="btn">فلتەر</button>
</form>

<div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:1rem">
  <div class="card"><b>By Day</b>
    <ul>
      {% for d,c in by_day.items()|list|sort %}
        <li>{{ d }} — {{ c }}</li>
      {% endfor %}
    </ul>
  </div>
  <div class="card"><b>By Game</b>
    <ul>
      {% for g,c in by_game.items()|list|sort %}
        <li>{{ g }} — {{ c }}</li>
      {% endfor %}
    </ul>
  </div>
  <div class="card"><b>By Variant</b>
    <ul>
      {% for v,c in by_variant.items()|list|sort %}
        <li>{{ v or '(empty)' }} — {{ c }}</li>
      {% endfor %}
    </ul>
  </div>
  <div class="card"><b>By Room</b>
    <ul>
      {% for r,c in by_room.items()|list|sort %}
        <li>{{ r or '(empty)' }} — {{ c }}</li>
      {% endfor %}
    </ul>
  </div>
  <div class="card"><b>By Platform</b>
    <ul>
      {% for p,c in by_platform.items()|list|sort %}
        <li>{{ p or '(empty)' }} — {{ c }}</li>
      {% endfor %}
    </ul>
  </div>
</div>

<h3 style="margin-top:1rem">Recent ({{ rows_head|length }})</h3>
<div class="table-responsive">
<table class="table">
  <thead><tr>
    <th>#</th><th>Game</th><th>Variant</th><th>Room</th><th>Platform</th><th>When</th>
  </tr></thead>
  <tbody>
    {% for r in rows_head %}
      <tr>
        <td>{{ loop.index }}</td>
        <td>{{ r.get('game_id') }}</td>
        <td>{{ r.get('variant') or '' }}</td>
        <td>{{ r.get('room') or '' }}</td>
        <td>{{ r.get('platform') or '' }}</td>
        <td>{{ human(r.get('ts')) }}</td>
      </tr>
    {% endfor %}
  </tbody>
</table>
</div>
{% endblock %}
"""
        return render_template_string(
            html,
            rows_head=rows_head,
            by_day=by_day,
            by_game=by_game,
            by_variant=by_variant,
            by_room=by_room,
            by_platform=by_platform,
            human=_human_date
        )

    @app.route('/admin/games/<int:game_id>/ads-analytics')
    def admin_game_ads_analytics(game_id):
        args = request.args.to_dict(flat=True)
        args['game_id'] = game_id
        qs = '&'.join([f"{k}={v}" for k, v in args.items() if v is not None and v != ''])
        return redirect(url_for('admin_ads_analytics') + (('?' + qs) if qs else ''))
# ==== END ANALYTICS ====
