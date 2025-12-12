(function(){
  const board = document.getElementById('board');
  const startBtn = document.getElementById('start');
  const resetBtn = document.getElementById('reset');
  const scoreEl = document.getElementById('score');
  const timeEl = document.getElementById('time');
  const bestEl = document.getElementById('best');

  const fruits = [
    {emoji:'🍎', cls:'apple'},
    {emoji:'🍌', cls:'banana'},
    {emoji:'🍇', cls:'grape'},
    {emoji:'🥝', cls:'kiwi'},
    {emoji:'🍊', cls:'orange'}
  ];

  let score = 0, time = 30, timer = null, spawnTimer = null, running = false;
  bestEl.textContent = localStorage.getItem('fruit_best') || '0';

  function rand(min,max){ return Math.floor(Math.random()*(max-min+1))+min; }

  function spawnFruit(){
    const f = fruits[rand(0, fruits.length-1)];
    const el = document.createElement('div');
    el.className = 'fruit '+f.cls;
    el.style.left = rand(0, board.clientWidth-56)+'px';
    el.style.top = rand(0, board.clientHeight-56)+'px';
    el.innerHTML = '<span class="badge">+'+rand(1,3)+'</span>'+f.emoji;
    const val = Number(el.querySelector('.badge').textContent.replace('+',''));
    el.addEventListener('click', ()=>{
      score += val;
      window.__score = score;
      scoreEl.textContent = score;
      el.remove();
      toast('+'+val+' points');
    });
    board.appendChild(el);
    // remove if not clicked
    setTimeout(()=>{ if (el && el.parentNode) el.remove(); }, rand(1000, 2500));
  }

  function toast(msg){
    let t = document.querySelector('.toast');
    if(!t){
      t = document.createElement('div'); t.className='toast';
      document.body.appendChild(t);
    }
    t.textContent = msg;
    requestAnimationFrame(()=>{ t.classList.add('show'); });
    setTimeout(()=> t.classList.remove('show'), 500);
  }

  function tick(){
    time -= 1;
    timeEl.textContent = time;
    if (time <= 0){
      stop();
      const best = Math.max(score, Number(localStorage.getItem('fruit_best')||0));
      localStorage.setItem('fruit_best', String(best));
      bestEl.textContent = best;
      toast('Level complete! Score: '+score);
      try{ maybeShowAd(); }catch(e){}
    }
  }

  function start(){
    if(running) return;
    running = true;
    score = 0; time = 30;
    scoreEl.textContent = score; timeEl.textContent = time;
    timer = setInterval(tick, 1000);
    spawnTimer = setInterval(spawnFruit, 350);
  }

  function stop(){
    running = false;
    clearInterval(timer); clearInterval(spawnTimer);
    timer = spawnTimer = null;
  }

  function reset(){
    stop();
    score = 0; time = 30;
    scoreEl.textContent = score; timeEl.textContent = time;
    board.innerHTML = '';
  }

  startBtn.addEventListener('click', start);
  resetBtn.addEventListener('click', reset);
})();