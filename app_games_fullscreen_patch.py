
# ==== GAMES PLAY (ALWAYS IFRAME + FULLSCREEN) ====
def _install_games_play_fullscreen(app):
    from flask import request, render_template

    def _get_game_local(game_id:int):
        try:
            if '_games_fetch' in globals():
                return _games_fetch(game_id)  # existing helper if present
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
        room = request.args.get('room', '').strip() or None
        # Always render template with iframe; if external blocks embedding, user can "Open in new tab"
        try:
            return render_template('admin/games/play.html', game=game, play_url=play_url, room=room)
        except Exception:
            return render_template('games/play.html', game=game, play_url=play_url, room=room)

    # Guarded registration
    if 'games_play' not in app.view_functions:
        app.add_url_rule('/games/<int:game_id>/play', endpoint='games_play', view_func=games_play, methods=['GET'])
# ==== END ====
