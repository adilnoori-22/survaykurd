# ==== BEGIN: GAMES ROUTES PATCH (admin template) ====
from flask import Blueprint, request, jsonify, render_template, redirect, url_for

games_bp = Blueprint('games_bp', __name__)

_ROOMS = {}

def _get_game(game_id:int):
    try:
        if '_games_fetch' in globals():
            return _games_fetch(game_id)  # type: ignore
    except Exception:
        pass
    return {
        'id': game_id,
        'title': f'Game #{game_id}',
        'play_url': '/static/games/fruit-clicker/index.html',
        'embed_html': None,
        'is_active': 1,
    }

@games_bp.route('/games/<int:game_id>/play')
def games_play(game_id: int):
    game = _get_game(game_id)
    play_url = (game or {}).get('play_url') or ''
    is_abs = play_url.startswith('http://') or play_url.startswith('https://')
    is_rel = play_url.startswith('/')
    room = request.args.get('room', '').strip() or None

    if is_abs:
        return redirect(play_url)
    elif is_rel:
        return render_template('admin/games/play.html', game=game, play_url=play_url, room=room)
    else:
        return render_template('admin/games/play.html', game=game, play_url=None, room=room)

@games_bp.get('/api/rooms/list')
def rooms_list():
    game_id = request.args.get('game_id', type=int)
    if not game_id:
        return jsonify({'ok': False, 'error': 'game_id required'}), 400
    rooms = _ROOMS.get(game_id, [])
    return jsonify({'ok': True, 'rooms': rooms})

@games_bp.post('/api/rooms/create')
def rooms_create():
    data = request.get_json(silent=True) or request.form or {}
    game_id = int(data.get('game_id', 0))
    if not game_id:
        return jsonify({'ok': False, 'error': 'game_id required'}), 400
    name = (data.get('roomname') or data.get('name') or '').strip() or 'public'
    code = (data.get('code') or '').strip() or name
    rooms = _ROOMS.setdefault(game_id, [])
    for r in rooms:
        if r.get('code') == code:
            return jsonify({'ok': True, 'room': r, 'created': False})
    room = {'code': code, 'name': name}
    rooms.append(room)
    return jsonify({'ok': True, 'room': room, 'created': True})

@games_bp.post('/api/rooms/join')
def rooms_join():
    data = request.get_json(silent=True) or request.form or {}
    game_id = int(data.get('game_id', 0))
    code = (data.get('code') or '').strip()
    if not (game_id and code):
        return jsonify({'ok': False, 'error': 'game_id and code required'}), 400
    url = url_for('games_bp.games_play', game_id=game_id, room=code)
    return jsonify({'ok': True, 'room': {'code': code, 'name': code}, 'url': url})

try:
    app  # type: ignore  # noqa: F401
    if 'games_bp' not in [bp.name for bp in app.blueprints.values()]:
        app.register_blueprint(games_bp)
except Exception:
    pass
# ==== END: GAMES ROUTES PATCH (admin template) ====
