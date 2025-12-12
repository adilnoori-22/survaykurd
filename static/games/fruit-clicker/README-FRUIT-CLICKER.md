
# Fruit Clicker – HTML5 Mini Game

This folder was added to your project at:
`static/games/fruit-clicker/`

## 1) How to "register" the game in your app

**Option A – via Admin UI (preferred):**
1. Start your Flask app.
2. Go to **/admin/games** → **New** (or similar).
3. Fill the form:
   - **Title**: Fruit Clicker
   - **Thumbnail URL**: /static/games/fruit-clicker/thumb.png  (optional; add your image)
   - **Play URL**: /static/games/fruit-clicker/index.html
   - **Embed HTML** (optional): `<iframe src="/static/games/fruit-clicker/index.html" width="960" height="580" style="border:0;border-radius:14px;overflow:hidden"></iframe>`
   - **Points override**: 0 (the game manages its own points)
   - **Min seconds override**: 0
   - **Active**: ✓
4. Save. It should now appear on the Games page.

**Option B – manual insert (SQLite):**
If your app stores games in SQLite, insert a row similar to:
```sql
INSERT INTO games (title, thumbnail_url, play_url, embed_html, is_active)
VALUES ('Fruit Clicker', '/static/games/fruit-clicker/thumb.png',
        '/static/games/fruit-clicker/index.html',
        '<iframe src="/static/games/fruit-clicker/index.html" width="960" height="580" style="border:0;border-radius:14px;overflow:hidden"></iframe>',
        1);
```
(Adjust the table/columns to match your schema.)

## 2) Ads / Hooks (optional)
The game calls `maybeShowAd()` at level completion. If your app defines `showInterstitial` and/or `onLevelComplete`, they will be invoked. Otherwise, it does nothing safely.

## 3) Test directly
Open: `http://127.0.0.1:5000/static/games/fruit-clicker/index.html`

## 4) Suggested button in templates
If you want a **Play** button somewhere:
```html
<a class="btn" href="/static/games/fruit-clicker/index.html" target="_blank">Play Fruit Clicker</a>
```

## 5) Assets
A placeholder `thumb.png` is not included. Add your image at:
`static/games/fruit-clicker/thumb.png`

