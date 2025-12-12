// --- portal.js (enhanced) ---
function playGame(id){
  const room = document.querySelector(`#room-${id}`)?.value || 'public';
  window.location.href = `/portal/game/${id}?room=${encodeURIComponent(room)}`;
}

function toggleFull(){
  const f = document.getElementById('gameframe');
  if(!f) return;
  if (f.requestFullscreen) f.requestFullscreen();
  else if (f.webkitRequestFullscreen) f.webkitRequestFullscreen();
  else if (f.msRequestFullscreen) f.msRequestFullscreen();
}

// wallet auto-refresh
setInterval(()=>{
  fetch('/api/wallet').then(r=>r.json()).then(j=>{
    if(j.ok){
      const el=document.getElementById('wallet');
      if(el) el.textContent=j.wallet;
    }
  });
}, 10000);

// passive earn (demo)
setInterval(()=>{
  fetch('/api/earn', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({seconds:30})
  }).then(r=>r.json()).then(j=>{
    if(j.ok){
      const el=document.getElementById('wallet');
      if(el) el.textContent=j.wallet;
    }
  });
}, 30000);

// --- NEW: rooms ---
async function createRoom(gameId){
  try{
    const res = await fetch('/api/rooms', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({game_id: gameId})
    });
    const j = await res.json();
    if(!j.ok) throw new Error(j.error || 'room create failed');
    // show minimal UI
    alert(`ژوور دروست کرا: ${j.room}\n\nبەستەری هاوبەشی: ${location.origin}${j.url}`);
    // open directly
    window.location.href = j.url;
  }catch(err){
    alert('هەڵە لە دروستکردنی ژوور: ' + err.message);
  }
}

function joinRoom(gameId){
  const inp = document.querySelector(`#room-${gameId}`);
  const code = (inp && inp.value || '').trim() || 'public';
  window.location.href = `/portal/game/${gameId}?room=${encodeURIComponent(code)}`;
}

async function copyRoomCode(){
  const el = document.getElementById('room-code');
  if(!el) return;
  try{
    await navigator.clipboard.writeText(el.innerText.trim());
    el.dataset.copied = '1';
    setTimeout(()=>{ el.dataset.copied=''; }, 1200);
  }catch(_){}
}

async function copyRoomLink(){
  const el = document.getElementById('room-link');
  if(!el) return;
  try{
    await navigator.clipboard.writeText(el.href);
    el.dataset.copied = '1';
    setTimeout(()=>{ el.dataset.copied=''; }, 1200);
  }catch(_){}
}
// joinRoom هەمانە
function joinRoom(id){
  const inp = document.querySelector(`#room-${id}`);
  const code = (inp && inp.value || '').trim() || 'public';
  window.location.href = `/portal/game/${id}?room=${encodeURIComponent(code)}`;
}

// دروستکردنی ژوور بە ناو
async function createRoom(id){
  const nameEl = document.querySelector(`#roomname-${id}`);
  const title = (nameEl && nameEl.value || '').trim();
  try{
    const r = await fetch('/api/rooms', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({game_id:id, title})
    });
    const j = await r.json();
    if(!j.ok) throw new Error(j.error||'failed');
    alert(`ژوور دروستکرا:\nکۆد: ${j.room}${title?`\nناو: ${title}`:''}`);
    window.location.href = j.url;
  }catch(e){
    alert('هەڵە لە دروستکردنی ژوور: '+e.message);
  }
}

// لیستی ژوورە کۆتاهەکان
async function listRooms(id){
  try{
    const r = await fetch(`/api/rooms/list?game_id=${id}`);
    const j = await r.json();
    if(!j.ok) return;
    const box = document.getElementById(`rooms-${id}`);
    if(!box) return;
    box.innerHTML = '';
    j.rooms.forEach(R=>{
      const a = document.createElement('a');
      a.className = 'pill';
      a.href = `/portal/game/${id}?room=${encodeURIComponent(R.code)}`;
      a.textContent = (R.title||R.code);
      box.appendChild(a);
    });
  }catch(_){}
}

// ریکلام نوێ بکە
async function refreshAd(){
  try{
    const r = await fetch('/api/ads/next');
    const j = await r.json();
    const box = document.getElementById('ad-box');
    if(!box) return;
    if(!j.ok || !j.ad){
      box.innerHTML = `<div class="muted">ریکلامی چالاک نییە.</div>`;
      return;
    }
    box.innerHTML = `
      <a href="${j.ad.click_url}" target="_blank" rel="noopener">
        <img src="${j.ad.image_url}" alt="${j.ad.title||'Ad'}" style="max-width:100%;height:auto;border-radius:10px">
      </a>
      <div class="muted">${j.ad.title||''}</div>
    `;
  }catch(_){}
}

window.createRoom = createRoom;
window.joinRoom = joinRoom;
window.copyRoomCode = copyRoomCode;
window.copyRoomLink = copyRoomLink;
