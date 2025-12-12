
// ==== BEGIN: PORTAL (rooms) FIXED ====
// Requires endpoints:
//  GET  /api/rooms/list?game_id=ID
//  POST /api/rooms/create {game_id, roomname}
//  POST /api/rooms/join {game_id, code}

async function _api(url, opts) {
  const r = await fetch(url, Object.assign({headers: {'Content-Type':'application/json'}}, opts||{}));
  let j = null;
  try { j = await r.json(); } catch(e) {}
  if (!r.ok) throw (j && j.error) || (j && JSON.stringify(j)) || ('HTTP '+r.status);
  return j || {};
}

function _val(id) {
  const el = document.getElementById(id);
  return el ? el.value.trim() : '';
}

function _roomsContainer(gameId){
  return document.getElementById('rooms-'+gameId);
}

async function listRooms(gameId){
  try{
    const j = await _api('/api/rooms/list?game_id='+encodeURIComponent(gameId));
    const box = _roomsContainer(gameId);
    if(!box) return;
    box.innerHTML='';
    const rooms = j.rooms || [];
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
      a.target = '_blank';
      a.rel = 'noopener';
      box.appendChild(a);
    });
  }catch(e){
    console.warn('listRooms failed:', e);
  }
}

async function createRoom(gameId){
  try{
    const name = _val('roomname-'+gameId) || 'public';
    const j = await _api('/api/rooms/create', {
      method:'POST', body: JSON.stringify({game_id: gameId, roomname: name})
    });
    await listRooms(gameId);
    alert('ژوور دروست کرا: '+ (j.room && (j.room.name || j.room.code)));
  }catch(e){
    alert('نەیتوانرا ژوور دروست بکرێت: '+ e);
  }
}

async function joinRoom(gameId){
  try{
    const code = _val('room-'+gameId) || 'public';
    const j = await _api('/api/rooms/join', {
      method:'POST', body: JSON.stringify({game_id: gameId, code})
    });
    if (j && j.url){
      window.open(j.url, '_blank', 'noopener');
      return;
    }
    // Fallback: go to internal play
    window.open('/games/'+gameId+'/play?room='+encodeURIComponent(code), '_blank', 'noopener');
  }catch(e){
    alert('نەیتوانرا بەشداری بكرێت: '+ e);
  }
}

// Expose globals expected by template
window.listRooms = listRooms;
window.createRoom = createRoom;
window.joinRoom = joinRoom;
// ==== END: PORTAL (rooms) FIXED ====
