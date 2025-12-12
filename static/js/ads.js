
/*! Lightweight interstitial UI (RTL-friendly) */
(function(){
  if (window.__AD_UI_LOADED__) return; window.__AD_UI_LOADED__ = true;

  // --- Helpers ---
  function qs(k){ var m = location.search.match(new RegExp('[?&]'+k+'=([^&]+)')); return m?decodeURIComponent(m[1]):''; }
  var ADTEST = qs('adtest') === '1';

  function el(tag, props, children){
    var e = document.createElement(tag);
    if (props){
      for (var k in props){
        if (k === 'style'){ for (var s in props.style){ e.style[s] = props.style[s]; } }
        else if (k === 'class'){ e.className = props[k]; }
        else if (k === 'text'){ e.textContent = props[k]; }
        else e.setAttribute(k, props[k]);
      }
    }
    if (children && children.length){ children.forEach(function(c){ if (c) e.appendChild(c); }); }
    return e;
  }

  function mountOnceStyle(){
    if (document.getElementById('adui-style')) return;
    var css = `
      .adui-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.6);backdrop-filter:saturate(120%) blur(1.5px);display:flex;align-items:center;justify-content:center;z-index:999999;}
      .adui-modal{background:#0f172a;color:#e5e7eb;border:1px solid #1f2937;border-radius:16px;box-shadow:0 10px 40px rgba(0,0,0,.45);width:min(560px,92vw);max-height:86vh;display:flex;flex-direction:column;overflow:hidden;direction:rtl;}
      .adui-head{display:flex;align-items:center;justify-content:space-between;padding:.8rem 1rem;border-bottom:1px solid #1f2937;}
      .adui-title{font-weight:800;font-size:1.05rem;margin:0 auto 0 0;display:flex;gap:.5rem;align-items:center;}
      .adui-close{appearance:none;border:0;background:#111827;color:#e5e7eb;width:32px;height:32px;border-radius:8px;display:flex;align-items:center;justify-content:center;cursor:not-allowed;opacity:.6}
      .adui-close.enabled{cursor:pointer;opacity:1}
      .adui-body{padding:1rem}
      .adui-meta{font-family:ui-monospace, SFMono-Regular, Menlo, monospace; background:#0b1220; border:1px dashed #334155; color:#cbd5e1; border-radius:10px; padding:.8rem; margin-top:.6rem; word-break:break-word; white-space:pre-wrap;}
      .adui-foot{display:flex;gap:.6rem;justify-content:flex-start;padding:0 1rem 1rem}
      .adui-btn{appearance:none;border:0;background:#0ea5e9;color:#06233a;font-weight:700;border-radius:10px;padding:.55rem 1rem;cursor:not-allowed;opacity:.8}
      .adui-btn.enabled{cursor:pointer;opacity:1}
      .adui-badge{font-size:.75rem;color:#94a3b8}
      @media (max-width: 420px){ .adui-modal{width:94vw} }
    `;
    var st = el('style', {id:'adui-style'}); st.appendChild(document.createTextNode(css)); document.head.appendChild(st);
  }

  function disableScroll(disabled){
    try{
      if (disabled){
        document.documentElement.style.overflow = 'hidden';
        document.body.style.overflow = 'hidden';
      }else{
        document.documentElement.style.overflow = '';
        document.body.style.overflow = '';
      }
    }catch(e){}
  }

  function showInterstitial(ad){
    // ad: {id, unit, html?, image?, meta?}
    mountOnceStyle();
    disableScroll(true);

    var backdrop = el('div', {class:'adui-backdrop'});
    var modal = el('div', {class:'adui-modal'});

    var title = el('div', {class:'adui-title'}, [
      el('span', {text:'ڕیکلامی ناوخۆ'}),
      ADTEST ? el('span', {class:'adui-badge', text:'(adtest)'}): null
    ]);
    var closeBtn = el('button', {class:'adui-close', 'aria-label':'Close', title:'داخستن'}, [el('span', {text:'×'})]);

    var head = el('div', {class:'adui-head'}, [title, closeBtn]);

    var body = el('div', {class:'adui-body'});
    // Creative area
    if (ad && ad.html){
      var wrap = el('div'); wrap.innerHTML = ad.html; body.appendChild(wrap);
    } else if (ad && ad.image){
      var img = el('img', {src:ad.image, style:{width:'100%', borderRadius:'10px'}}); body.appendChild(img);
    } else {
      // minimal text
      body.appendChild(el('div', {text:'ئێمە ڕیکلامێک نیشان دا.'}));
    }

    // Meta (debug only in adtest)
    if (ADTEST){
      var metaTxt = JSON.stringify({ad_id: ad && ad.id, unit: ad && ad.unit, meta: ad && ad.meta || {}}, null, 2);
      body.appendChild(el('div', {class:'adui-meta'}, [document.createTextNode(metaTxt)]));
    }

    var foot = el('div', {class:'adui-foot'});
    var cta = el('button', {class:'adui-btn', text:'بەردەوامبوون'});
    foot.appendChild(cta);

    modal.appendChild(head); modal.appendChild(body); modal.appendChild(foot);
    backdrop.appendChild(modal);
    document.body.appendChild(backdrop);

    // Countdown (skip in adtest)
    var seconds = (window.AD_COUNTDOWN_SEC != null) ? Number(window.AD_COUNTDOWN_SEC) : 2;
    if (ADTEST) seconds = 0;
    function enable(){
      cta.classList.add('enabled');
      closeBtn.classList.add('enabled');
      cta.style.cursor = 'pointer';
      closeBtn.style.cursor = 'pointer';
      cta.disabled = false;
    }
    function disable(){
      cta.classList.remove('enabled');
      closeBtn.classList.remove('enabled');
      cta.style.cursor = 'not-allowed';
      closeBtn.style.cursor = 'not-allowed';
      cta.disabled = true;
    }
    disable();
    var t = seconds;
    function tick(){
      if (t <= 0){ enable(); cta.textContent = 'بەردەوامبوون'; return; }
      cta.textContent = 'بەردەوامبوون ('+t+'s)';
      t -= 1;
      setTimeout(tick, 1000);
    }
    tick();

    function cleanup(){
      try{ document.body.removeChild(backdrop); }catch(e){}
      disableScroll(false);
      if (typeof window.onInterstitialClosed === 'function'){
        try{ window.onInterstitialClosed(ad); }catch(e){}
      }
    }

    cta.addEventListener('click', function(){ if (!cta.classList.contains('enabled')) return; cleanup(); });
    closeBtn.addEventListener('click', function(){ if (!closeBtn.classList.contains('enabled')) return; cleanup(); });
  }

  // expose
  window.showInterstitial = showInterstitial;
})();
