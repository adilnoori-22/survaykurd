// ==== Fullscreen helper for all games ====
(function(){
  function ready(fn){ if (document.readyState!=='loading') fn(); else document.addEventListener('DOMContentLoaded', fn); }
  function canFS(){ var d=document; var el=d.documentElement; return !!(el.requestFullscreen||el.webkitRequestFullscreen||el.mozRequestFullScreen||el.msRequestFullscreen); }
  function reqFS(el){
    if (el.requestFullscreen) return el.requestFullscreen();
    if (el.webkitRequestFullscreen) return el.webkitRequestFullscreen();
    if (el.mozRequestFullScreen) return el.mozRequestFullScreen();
    if (el.msRequestFullscreen) return el.msRequestFullscreen();
  }
  function exitFS(){
    var d=document;
    if (d.exitFullscreen) return d.exitFullscreen();
    if (d.webkitExitFullscreen) return d.webkitExitFullscreen();
    if (d.mozCancelFullScreen) return d.mozCancelFullScreen();
    if (d.msExitFullscreen) return d.msExitFullscreen();
  }
  function isFS(){
    var d=document;
    return !!(d.fullscreenElement||d.webkitFullscreenElement||d.mozFullScreenElement||d.msFullscreenElement);
  }

  ready(function(){
    if (!canFS()) return;
    var target = document.querySelector('#game, canvas, iframe, .game, .unity-container, #unity-container') || document.body;

    var btn = document.createElement('button');
    btn.type='button';
    btn.innerHTML = '⤢ فول-سکرین';
    btn.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:99998;background:#0f172a;color:#e2e8f0;border:1px solid #334155;border-radius:10px;padding:10px 14px;font-weight:800;cursor:pointer;box-shadow:0 6px 20px rgba(0,0,0,.35)';
    btn.title = 'فول سکرین';

    btn.onclick = function(){
      if (isFS()) { exitFS(); return; }
      reqFS(target);
    };

    document.body.appendChild(btn);
    document.addEventListener('fullscreenchange', function(){
      btn.textContent = isFS() ? '⤡ دەرچوون' : '⤢ فول-سکرین';
    });
  });
})();
