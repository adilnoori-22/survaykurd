
# ==== ROOMS ROUTES (SAFE) ====
def _rooms_install_routes_on(app):
    from flask import request, jsonify, render_template, redirect, url_for

    if not hasattr(app, '_ROOMS_STORE'):
        app._ROOMS_STORE = {}

    def _get_game_local(game_id:int):
        try:
            if '_games_fetch' in globals():
                return _games_fetch(game_id)
        except Exception:
            pass
        return {
            'id': game_id,
            'title': f'Game #{game_id}',
            'play_url': '/static/games/fruit-clicker/index.html',
            'embed_html': None,
            'is_active': 1,
        }

    def games_play(game_id:int):
        game = _get_game_local(game_id)
        play_url = (game or {}).get('play_url') or ''
        is_abs = play_url.startswith('http://') or play_url.startswith('https://')
        is_rel = play_url.startswith('/')
        room = request.args.get('room', '').strip() or None
        if is_abs:
            return redirect(play_url)
        elif is_rel:
            try:
                return render_template('admin/games/play.html', game=game, play_url=play_url, room=room)
            except Exception:
                return render_template('games/play.html', game=game, play_url=play_url, room=room)
        else:
            try:
                return render_template('admin/games/play.html', game=game, play_url=None, room=room)
            except Exception:
                return render_template('games/play.html', game=game, play_url=None, room=room)

    def rooms_list():
        game_id = request.args.get('game_id', type=int)
        if not game_id:
            return jsonify({'ok': False, 'error': 'game_id required'}), 400
        return jsonify({'ok': True, 'rooms': app._ROOMS_STORE.get(game_id, [])})

    def rooms_create():
        data = request.get_json(silent=True) or request.form or {}
        game_id = int(data.get('game_id', 0))
        if not game_id:
            return jsonify({'ok': False, 'error': 'game_id required'}), 400
        name = (data.get('roomname') or data.get('name') or '').strip() or 'public'
        code = (data.get('code') or '').strip() or name
        rooms = app._ROOMS_STORE.setdefault(game_id, [])
        for r in rooms:
            if r.get('code') == code:
                return jsonify({'ok': True, 'room': r, 'created': False})
        room = {'code': code, 'name': name}
        rooms.append(room)
        return jsonify({'ok': True, 'room': room, 'created': True})

    def rooms_join():
        data = request.get_json(silent=True) or request.form or {}
        game_id = int(data.get('game_id', 0))
        code = (data.get('code') or '').strip()
        if not (game_id and code):
            return jsonify({'ok': False, 'error': 'game_id and code required'}), 400
        url = url_for('games_play', game_id=game_id, room=code)
        return jsonify({'ok': True, 'room': {'code': code, 'name': code}, 'url': url})

    def _add(rule, endpoint, view_func, methods):
        if endpoint in app.view_functions:
            return
        app.add_url_rule(rule, endpoint=endpoint, view_func=view_func, methods=methods)

    _add('/games/<int:game_id>/play', 'games_play', games_play, ['GET'])
    _add('/api/rooms/list', 'rooms_list', rooms_list, ['GET'])
    _add('/api/rooms/create', 'rooms_create', rooms_create, ['POST'])
    _add('/api/rooms/join', 'rooms_join', rooms_join, ['POST'])
# ==== END ROOMS ROUTES ====
