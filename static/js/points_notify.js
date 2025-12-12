
// points_notify.js — show toast whenever server replies with credited points
(function(){
  function toast(msg){
    var t = document.createElement('div');
    t.textContent = msg;
    t.style.position='fixed'; t.style.top='18px'; t.style.right='18px';
    t.style.background='rgba(34,197,94,.97)'; t.style.color='#fff'; t.style.padding='10px 14px';
    t.style.borderRadius='10px'; t.style.boxShadow='0 10px 20px rgba(0,0,0,.35)'; t.style.zIndex=100000;
    document.body.appendChild(t); setTimeout(function(){ try{t.remove();}catch(e){} }, 2200);
  }
  async function parseMaybeJSON(r){
    try{
      var ct = (r.headers && r.headers.get && r.headers.get('content-type'))||'';
      if (ct.indexOf('application/json')!==-1) return await r.clone().json();
      var txt = await r.clone().text();
      return JSON.parse(txt);
    }catch(e){ return null; }
  }
  // Patch fetch
  if (window.fetch){
    var _f = window.fetch;
    window.fetch = async function(){
      var r = await _f.apply(this, arguments);
      try{
        var j = await parseMaybeJSON(r);
        if (j && j.ok){
          if (typeof j.points === 'number' && j.points>0){ toast('+'+j.points+' pts'); }
          if (typeof j.winner_points === 'number' && j.winner_points>0){ toast('+'+j.winner_points+' pts (win)'); }
        }
      }catch(e){}
      return r;
    };
  }
  // Patch XHR
  if (window.XMLHttpRequest){
    var O = window.XMLHttpRequest;
    function W(){ var x=new O(); var _open=x.open; var _send=x.send; x.open=function(){_open.apply(x,arguments)}; x.send=function(){
      x.addEventListener('load', function(){
        try{
          var j = JSON.parse(x.responseText);
          if (j && j.ok){
            if (typeof j.points === 'number' && j.points>0){ toast('+'+j.points+' pts'); }
            if (typeof j.winner_points === 'number' && j.winner_points>0){ toast('+'+j.winner_points+' pts (win)'); }
          }
        }catch(e){}
      });
      _send.apply(x, arguments);
    }; return x; }
    window.XMLHttpRequest = W;
  }
})();
