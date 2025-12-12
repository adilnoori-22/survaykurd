
// stake_ui.js — room stake panel (Start/Join/Finish) with 80/20 payout
(function(){
  function qs(k){ var m = location.search.match(new RegExp('[?&]'+k+'=([^&]+)')); return m ? decodeURIComponent(m[1]) : ''; }
  var GAME_ID = (typeof window!=='undefined' && (window.AD_GAME_ID || window.GAME_ID)) || Number(qs('game_id')) || 0;
  var ROOM    = (typeof window!=='undefined' && (window.AD_ROOM || window.__ROOM__)) || qs('room') || 'public';
  if (!GAME_ID) return; // only on play pages

  // ---- net helpers ----
  async function postJSON(url, data){
    const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, credentials:'same-origin', body: JSON.stringify(data||{})});
    const ct = r.headers.get('content-type')||'';
    let j = null;
    try { j = ct.indexOf('application/json')!==-1 ? await r.json() : JSON.parse(await r.text()); } catch(_){}
    if (!r.ok || !j || !j.ok){ throw new Error((j&&j.error)||('HTTP '+r.status)); }
    return j;
  }

  // ---- UI ----
  function el(tag, props, children){
    var e = document.createElement(tag);
    if (props){
      for (var k in props){
        if (k==='class') e.className = props[k];
        else if (k==='style'){ for (var s in props.style){ e.style[s] = props.style[s]; } }
        else if (k==='text') e.textContent = props[k];
        else if (k==='html') e.innerHTML = props[k];
        else e.setAttribute(k, props[k]);
      }
    }
    (children||[]).forEach(function(c){ e.appendChild(c); });
    return e;
  }
  function badge(text){
    return el('span', {style:{padding:'2px 6px',border:'1px solid rgba(255,255,255,.16)',borderRadius:'8px',fontSize:'.82rem',opacity:.9}}, [document.createTextNode(text)]);
  }
  function toast(msg, ok){
    var t = el('div', {style:{
      position:'fixed', bottom:'18px', right:'18px', background: ok ? 'rgba(34,197,94,.95)' : 'rgba(239,68,68,.95)',
      color:'#fff', padding:'10px 14px', borderRadius:'10px', boxShadow:'0 10px 20px rgba(0,0,0,.35)', zIndex: 99999
    }, text: msg});
    document.body.appendChild(t);
    setTimeout(function(){ try{ t.remove(); }catch(e){} }, 2200);
  }

  function panel(){
    var wrap = el('div', {id:'stake-panel', style:{
      position:'fixed', top:'84px', left:'12px', zIndex:9999, width:'280px',
      background:'rgba(10,16,30,.92)', border:'1px solid rgba(255,255,255,.14)',
      borderRadius:'14px', padding:'12px', boxShadow:'0 10px 25px rgba(0,0,0,.35)', color:'#e6fbff'
    }});
    var head = el('div', {style:{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:'8px'}});
    head.appendChild(el('div', {style:{fontWeight:'700'} , text:'Stake Match (80/20)'}));
    var meta = el('div', {style:{display:'flex',gap:'6px',alignItems:'center'}});
    meta.appendChild(badge('Game '+GAME_ID));
    meta.appendChild(badge('Room '+ROOM));
    head.appendChild(meta);
    wrap.appendChild(head);

    var g = el('div', {style:{display:'grid',gridTemplateColumns:'1fr 1fr',gap:'8px'}});

    // Start
    var stakeIn = el('input', {type:'number', min:'1', placeholder:'Stake pts', style:{width:'100%',padding:'8px',borderRadius:'10px',border:'1px solid rgba(255,255,255,.14)', background:'#0b1220', color:'#e6fbff'}});
    var btnStart = el('button', {text:'Start', style:{padding:'8px',borderRadius:'10px',border:'1px solid rgba(255,255,255,.14)',cursor:'pointer',background:'rgba(255,255,255,.06)',color:'#e6fbff'}});
    btnStart.onclick = async function(){
      var stake = parseInt(stakeIn.value||'0',10);
      if (!stake || stake<=0){ stakeIn.focus(); return; }
      btnStart.disabled = true;
      try{
        var j = await postJSON('/api/rooms/match/start', {game_id: GAME_ID, room: ROOM, stake: stake});
        window.__LAST_MATCH_ID__ = j.match_id;
        lastId.value = String(j.match_id);
        toast('Started match #'+j.match_id, true);
      }catch(e){ toast('Start failed: '+e.message, false); }
      btnStart.disabled = false;
    };

    // Join
    var lastId = el('input', {type:'number', min:'1', placeholder:'Match ID', style:{width:'100%',padding:'8px',borderRadius:'10px',border:'1px solid rgba(255,255,255,.14)', background:'#0b1220', color:'#e6fbff'}});
    var btnJoin = el('button', {text:'Join', style:{padding:'8px',borderRadius:'10px',border:'1px solid rgba(255,255,255,.14)',cursor:'pointer',background:'rgba(255,255,255,.06)',color:'#e6fbff'}});
    btnJoin.onclick = async function(){
      var mid = parseInt(lastId.value||'0',10);
      if (!mid){ lastId.focus(); return; }
      btnJoin.disabled = true;
      try{ await postJSON('/api/rooms/match/join', {match_id: mid}); toast('Joined match #'+mid, true); }
      catch(e){ toast('Join failed: '+e.message, false); }
      btnJoin.disabled = false;
    };

    // Finish
    var winUser = el('input', {type:'number', min:'1', placeholder:'Winner user_id', style:{width:'100%',padding:'8px',borderRadius:'10px',border:'1px solid rgba(255,255,255,.14)', background:'#0b1220', color:'#e6fbff'}});
    var btnFinish = el('button', {text:'Finish', style:{padding:'8px',borderRadius:'10px',border:'1px solid rgba(255,255,255,.14)',cursor:'pointer',background:'rgba(34,211,238,.10)',color:'#e6fbff'}});
    btnFinish.onclick = async function(){
      var mid = parseInt(lastId.value||'0',10);
      var wid = parseInt(winUser.value||'0',10);
      if (!mid){ lastId.focus(); return; }
      if (!wid){ winUser.focus(); return; }
      btnFinish.disabled = true;
      try{
        var j = await postJSON('/api/rooms/match/finish', {match_id: mid, winner_user_id: wid});
        toast('Win +'+j.winner_points+' | Admin +'+j.admin_cut, true);
      }catch(e){ toast('Finish failed: '+e.message, false); }
      btnFinish.disabled = false;
    };

    g.appendChild(stakeIn); g.appendChild(btnStart);
    g.appendChild(lastId);  g.appendChild(btnJoin);
    g.appendChild(winUser); g.appendChild(btnFinish);
    wrap.appendChild(g);

    // Drag to move
    var isDown=false, sx=0, sy=0, ox=0, oy=0;
    wrap.addEventListener('mousedown', function(ev){
      if (ev.target.tagName==='INPUT' || ev.target.tagName==='BUTTON') return;
      isDown=true; sx=ev.clientX; sy=ev.clientY; var r=wrap.getBoundingClientRect(); ox=r.left; oy=r.top; ev.preventDefault();
    });
    window.addEventListener('mousemove', function(ev){
      if (!isDown) return;
      var dx=ev.clientX-sx, dy=ev.clientY-sy;
      wrap.style.left = Math.max(8, ox+dx) + 'px';
      wrap.style.top  = Math.max(60, oy+dy) + 'px';
    });
    window.addEventListener('mouseup', function(){ isDown=false; });

    document.body.appendChild(wrap);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', panel);
  else panel();
})();
