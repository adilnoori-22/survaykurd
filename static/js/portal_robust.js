
// ==== PORTAL ROBUST ====
async function _api(url, opts) {
  const res = await fetch(url, Object.assign({
    headers: {'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'}
  }, opts||{}));
  const ct = res.headers.get('content-type') || '';
  let data = null, text = null;
  if (ct.includes('application/json')) {
    try { data = await res.json(); } catch(e) {}
  } else {
    try { text = await res.text(); } catch(e) {}
  }
  if (!res.ok) {
    const msg = (data && (data.error || data.message)) || (text || ('HTTP '+res.status));
    throw new Error(msg);
  }
  return data || {ok:true, html:text};
}

function _encode(obj){
  return Object.entries(obj).map(([k,v]) => 
    encodeURIComponent(k) + '=' + encodeURIComponent(v==null?'':String(v))
  ).join('&');
}

function _v(id){ const el = document.getElementById(id); return el ? el.value.trim() : ''; }
function _box(gameId){ return document.getElementById('rooms-'+gameId); }

async function listRooms(gameId){
  try{
    const j = await _api('/api/rooms/list?game_id='+encodeURIComponent(gameId));
    const box = _box(gameId); if(!box) return;
    box.innerHTML='';
    const rooms = (j && j.rooms) || [];
    if(!rooms.length){
      const em = document.createElement('div');
      em.className='muted';
      em.textContent='ھیچ ژوورێک نییە.';
      box.appendChild(em);
      return;
    }
    rooms.forEach(r => {
      const a = document.createElement('a');
      a.className='btn small';
      a.textContent = r.name || r.code;
      a.href = '/games/'+gameId+'/play?room='+encodeURIComponent(r.code);
      a.target = '_blank'; a.rel = 'noopener';
      box.appendChild(a);
    });
  }catch(e){
    alert('هەلە لە نوێکردنەوەی ژوورەکان: '+ e.message);
  }
}

async function createRoom(gameId){
  try{
    const body = _encode({game_id: gameId, roomname: _v('roomname-'+gameId) || 'public'});
    const j = await _api('/api/rooms/create', {method:'POST', body});
    await listRooms(gameId);
    alert('ژوور دروست کرا.');
  }catch(e){
    alert("هەڵە لە دروستکردنی ژوور: " + e.message);
  }
}

async function joinRoom(gameId){
  try{
    const body = _encode({game_id: gameId, code: _v('room-'+gameId) || 'public'});
    const j = await _api('/api/rooms/join', {method:'POST', body});
    if (j && j.url){
      window.open(j.url, '_blank', 'noopener'); return;
    }
    window.open('/games/'+gameId+'/play?room='+encodeURIComponent(_v('room-'+gameId) || 'public'), '_blank', 'noopener');
  }catch(e){
    alert("هەڵە لە بەشداری لە ژوور: " + e.message);
  }
}

window.listRooms = listRooms;
window.createRoom = createRoom;
window.joinRoom = joinRoom;
