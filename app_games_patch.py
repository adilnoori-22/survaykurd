
# ==== BEGIN: GAMES ROUTES PATCH ====
from flask import Blueprint, request, jsonify, render_template, redirect, url_for, abort
from urllib.parse import urlparse

games_bp = Blueprint('games_bp', __name__)

# --- Minimal storage for rooms (replace with your DB) ---
_ROOMS = {}  # key: game_id, value: list of {'code': 'public', 'name': 'My Room'}

def _get_game(game_id:int):
    """Replace with your real game accessor.

    Must return dict with keys: id, title, play_url (optional), embed_html (optional), is_active (int/bool)"""
    try:
        # Example adapters you might already have:
        if '_games_fetch' in globals():
            return _games_fetch(game_id)  # type: ignore # existing helper in your app
    except Exception:
        pass
    # Fallback: pretend there's a Fruit Clicker entry if none
    return {
        'id': game_id,
        'title': f'Game #{game_id}',
        'play_url': '/static/games/fruit-clicker/index.html',
        'embed_html': None,
        'is_active': 1,
    }

@games_bp.route('/games/<int:game_id>/play')
def games_play(game_id: int):
    """Internal play page.

    - If a full play_url exists (http/https) => redirect there

    - If a relative play_url exists => render our internal play.html with iframe

    - Else => show a minimal message

    """
    game = _get_game(game_id)
    play_url = (game or {}).get('play_url') or ''
    is_abs = play_url.startswith('http://') or play_url.startswith('https://')
    is_rel = play_url.startswith('/')

    # Allow passing room code e.g. /games/12/play?room=public
    room = request.args.get('room', '').strip() or None

    if is_abs:
        # External absolute URL -> redirect
        return redirect(play_url)
    elif is_rel:
        # Relative path -> show internal play page via iframe
        return render_template('games/play.html', game=game, play_url=play_url, room=room)
    else:
        # No play_url -> show info
        return render_template('games/play.html', game=game, play_url=None, room=room)

# ---- Rooms API ----
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
    # Avoid duplicates
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
    rooms = _ROOMS.get(game_id, [])
    # accept any code; optionally enforce existence:
    found = next((r for r in rooms if r.get('code') == code), {'code': code, 'name': code})
    # Return a URL to navigate to
    url = url_for('games_bp.games_play', game_id=game_id, room=code)
    return jsonify({'ok': True, 'room': found, 'url': url})

# Register the blueprint if not already
try:
    app  # type: ignore  # noqa: F401
    if 'games_bp' not in [bp.name for bp in app.blueprints.values()]:
        app.register_blueprint(games_bp)
except Exception:
    # If app isn't defined here, user will import and register manually.
    pass

# ==== END: GAMES ROUTES PATCH ====
