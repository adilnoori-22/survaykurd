// ==== AD HOOKS (A/B + CREDIT LOGGING, skip-click-games, variant HTML) ====
// Patched: force-show when ?adtest=1 (bypass all guards and triggers)
(function(){
  function qs(k){ var m = location.search.match(new RegExp('[?&]'+k+'=([^&]+)')); return m ? decodeURIComponent(m[1]) : ''; }
  var gameId = Number(qs('game_id')) || (typeof window!=='undefined' ? (window.AD_GAME_ID || null) : null);
  if (!gameId) return;

  function fetchJSON(url){
    return fetch(url, {credentials:'same-origin'}).then(function(r){
      var ct = r.headers.get('content-type') || '';
      if (!r.ok) return r.text().then(function(t){ throw new Error(t || ('HTTP '+r.status)); });
      if (ct.indexOf('application/json') !== -1) return r.json();
      return r.text().then(function(t){ try { return JSON.parse(t); } catch(e){ return {}; } });
    });
  }
  function now(){ return Date.now(); }
  function todayKey(){ var d=new Date(); return d.getFullYear()+"-"+(d.getMonth()+1)+"-"+d.getDate(); }
  function rand100(){ return Math.floor(Math.random()*100)+1; }
  function isMobile(){
    var ua = navigator.userAgent || "";
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(ua);
  }
  function getRoom(){ return qs('room') || (window.AD_ROOM || ''); }
  function platform(){ return isMobile() ? 'mobile' : 'desktop'; }

  var storeKey = function(k){ return 'ads:'+gameId+':'+k; };
  function getCount(){ return Number(sessionStorage.getItem(storeKey('count'))||0); }
  function incCount(){ sessionStorage.setItem(storeKey('count'), String(getCount()+1)); }
  function getLastTs(){ return Number(sessionStorage.getItem(storeKey('last_ts'))||0); }
  function setLastTs(t){ sessionStorage.setItem(storeKey('last_ts'), String(t||now())); }

  function getDaily(key){
    var k = storeKey('daily:'+key+':'+todayKey());
    return Number(localStorage.getItem(k) || 0);
  }
  function incDaily(key){
    var k = storeKey('daily:'+key+':'+todayKey());
    var v = Number(localStorage.getItem(k) || 0) + 1;
    localStorage.setItem(k, String(v));
  }

  function credit(ad, cfg, variantName){
    try{
      var payload = {
        game_id: gameId,
        ad_id: (ad && ad.id) || 'auto',
        variant: variantName || '',
        room: getRoom() || '',
        platform: platform(),
        event: 'view',
        meta: (ad && ad.meta) || {}
      };
      fetch('/api/ads/credit', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify(payload), credentials:'same-origin'
      }).catch(function(){});
    }catch(e){}
  }

  function tryShow(ad, cfg, variant){
    var unit = (variant && variant.ad_unit_id) || (cfg && cfg.ad_unit_id) || '';
    var payload = ad || {id:'auto', unit: unit, meta:{}};
    payload.unit = unit;
    payload.html = (variant && variant.html) || payload.html || null; // pass variant HTML if present
    if (typeof showInterstitial === 'function'){
      try {
        showInterstitial(payload);
        credit(payload, cfg, variant ? variant.name : '');
      } catch(e){}
    }
  }

  function withinSchedule(cfg){
    var f = (cfg.schedule_from||'').trim(), t = (cfg.schedule_to||'').trim();
    if (!f && !t) return true;
    try{
      var d = new Date();
      function toMin(s){ if(!s) return null; var a=s.split(':'); return (+a[0])*60 + (+a[1]); }
      var cur = d.getHours()*60 + d.getMinutes();
      var fm = toMin(f), tm = toMin(t);
      if (fm==null && tm==null) return true;
      if (fm!=null && tm!=null){
        if (fm <= tm) return (cur >= fm && cur <= tm);
        return (cur >= fm || cur <= tm);
      }
      if (fm!=null) return cur >= fm;
      if (tm!=null) return cur <= tm;
      return true;
    }catch(e){ return true; }
  }
  function allowedByRoom(cfg){
    var room = getRoom();
    var allow = cfg.room_allow||[], deny = cfg.room_deny||[];
    if (room && deny.indexOf(room) !== -1) return false;
    if (allow && allow.length){ return allow.indexOf(room) !== -1; }
    return true;
  }
  function allowedByPlatform(cfg){
    if (isMobile() && !cfg.platform_mobile) return false;
    if (!isMobile() && !cfg.platform_desktop) return false;
    return true;
  }

  // ======== PATCHED GUARDS ========
  function shouldShow(cfg, context){
    var adtest = (location.search.indexOf('adtest=1') !== -1);

    // ✅ PATCH: in adtest, bypass all guards & quotas
    if (adtest) return true;

    // Skip click games if configured (normal mode only)
    if (cfg.skip_click_games && window.AD_IS_CLICK_GAME) return false;

    // Normal guards
    if (cfg.skip_for_admins && cfg._is_admin) return false;
    if (!withinSchedule(cfg)) return false;
    if (!allowedByRoom(cfg)) return false;
    if (!allowedByPlatform(cfg)) return false;
    if (cfg.probability < 100 && rand100() > cfg.probability) return false;
    if (context && context.level && cfg.every_n_levels > 1){
      if ((context.level % cfg.every_n_levels) !== 0) return false;
    }

    var cnt = getCount();
    if (cfg.max_per_session && cnt >= cfg.max_per_session) return false;
    var last = getLastTs();
    if (cfg.cooldown_sec && last && ( (Date.now() - last) < cfg.cooldown_sec*1000 )) return false;
    if (cfg.daily_cap){
      var dcnt = getDaily('total');
      if (dcnt >= cfg.daily_cap) return false;
    }
    return true;
  }

  function pickVariant(cfg){
    var vOverride = qs('variant');
    var list = Array.isArray(cfg.variants) ? cfg.variants.slice() : [];
    if (vOverride){
      for (var i=0;i<list.length;i++){ if (list[i].name === vOverride) return list[i]; }
    }
    if (!list.length) return null;
    var sticky = sessionStorage.getItem(storeKey('variant'));
    if (sticky){
      try{
        var obj = JSON.parse(sticky);
        if (obj && obj.name){ return obj; }
      }catch(e){}
    }
    var total = 0;
    list.forEach(function(v){ total += Number(v.weight||0); });
    if (!total) return null;
    var r = Math.random() * total, acc = 0, chosen = null;
    for (var j=0;j<list.length;j++){
      acc += Number(list[j].weight||0);
      if (r <= acc){ chosen = list[j]; break; }
    }
    if (!chosen) chosen = list[list.length-1];
    sessionStorage.setItem(storeKey('variant'), JSON.stringify(chosen));
    return chosen;
  }

  function handle(cfg, context){
    if (!shouldShow(cfg, context)) return;
    var variant = pickVariant(cfg);
    tryShow({id: (context.tag||'auto')+':'+gameId, meta: context || {}}, cfg, variant);
    incCount(); setLastTs(Date.now());
    if (cfg.daily_cap) incDaily('total');
  }

  function init(){
      var FORCE = (typeof window!=='undefined' && window.AD_FORCE_PREROLL===true);

    fetchJSON('/api/ads/config?game_id='+encodeURIComponent(gameId))
    .then(function(j){
      var c = (j && j.config) || {};
      if (FORCE) { c.start = true; c.daily_cap = 0; }
      var adtest = (location.search.indexOf('adtest=1') !== -1);

      // ✅ PATCH: in adtest mode, force-show immediately (no trigger needed)
      if (adtest) {
        var d = Number(c.start_delay_ms || 0);
        setTimeout(function(){ handle(c, {tag:'adtest'}); }, d);
        return;
      }

      // Normal start trigger (or forced pre-roll)
      if (FORCE){
        setTimeout(function(){ handle(c, {tag:'force_start'}); }, 0);
      }
      // Normal start trigger
      if (c.start){
        var d2 = Number(c.start_delay_ms||0);
        setTimeout(function(){ handle(c, {tag:'start'}); }, d2);
      }

      // Mid/End level triggers
      if (c.level_end || c.mid_level){
        window.addEventListener('message', function(ev){
          var d = ev.data; if (!d) return;
          if (typeof d === 'string'){ try { d = JSON.parse(d); } catch(e){} }
          if (!d) return;
          if (c.level_end && (d.type==='level-complete' || d.level_complete)){
            var lvl = Number(d.level||d.lvl||d.stage||0)||0;
            handle(c, {tag:'level_end', level: lvl, payload:d});
          } else if (c.mid_level && (d.type==='ad-break' || d.mid_break)){
            var lvl2 = Number(d.level||0)||0;
            handle(c, {tag:'mid', level: lvl2, payload:d});
          }
        });
        window.onLevelComplete = function(p){ var l=(p&&p.level)||0; handle(c, {tag:'level_end', level:l, payload:p||{}}); };
        window.onAdBreak = function(p){ var l=(p&&p.level)||0; handle(c, {tag:'mid', level:l, payload:p||{}}); };
      }
    })
    .catch(function(e){ console.warn('ads config fetch failed:', e); });
  }

  // Defer a bit to let the game DOM load
  setTimeout(init, 200);
})();
