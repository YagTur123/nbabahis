const API = '/api';
let sDate=fmt(new Date()), sGame=null, sTeam=null, allP=[], sel=new Set(), curFilt='ALL', _pi=null;
let currentSgps = [];

const SORD = ['PTS','REB','AST','STL','BLK','TOV','PF','FG3M','FGM','FTM','FTA','FGA','FG3A','PRA','P+R','P+A','A+R','S+B'];
const SCOL = {'PTS':'t-pts','REB':'t-reb','AST':'t-ast','STL':'t-stl','BLK':'t-blk','TOV':'t-tov','PF':'t-pf','FG3M':'t-fg3m','FGM':'t-fgm','FTM':'t-ftm','FTA':'t-fta','FGA':'t-fga','FG3A':'t-fg3a','PRA':'t-pra','P+R':'t-pr','P+A':'t-pa','A+R':'t-ar','S+B':'t-sb'};
function fmtBaremLine(line){ return (line!=null && line!=='' && !Number.isNaN(Number(line))) ? Number(line).toFixed(1) : '—'; }
function fmtBarem(p){ return fmtBaremLine(p && p.line); }

document.getElementById('datepick').value=sDate;
document.getElementById('bt-datepick').value=sDate;
checkStatus(); loadHist(); loadInjuries();

// ─── STATUS ───
async function checkStatus(){
  try {
    const data=await fetch(`${API}/status`).then(r=>r.json());
    const m=document.getElementById('ml-status'), cm=document.getElementById('cfg-ml');
    if(data.advanced_ml){
      m.textContent='ML: XGB/LGB Aktif'; m.style.color='var(--green)';
      if(cm){ cm.textContent='XGBoost/LightGBM Aktif'; cm.style.color='var(--green)'; }
    } else {
      m.textContent='ML: Sklearn (Fallback)'; m.style.color='var(--amber)';
      if(cm){ cm.textContent='Sadece Sklearn (Fallback)'; cm.style.color='var(--amber)'; }
    }
    const o=document.getElementById('odds-api-status'), co=document.getElementById('cfg-odds');
    if(data.odds_configured){
      o.textContent='Odds API: Bağlı'; o.style.color='var(--blue)';
      if(co){ co.textContent='Bağlı / Aktif'; co.style.color='var(--blue)'; }
    } else {
      o.textContent='Odds API: Yok'; o.style.color='var(--muted)';
      if(co){ co.textContent='Yapılandırılmamış (Ayarlardan giriniz)'; co.style.color='var(--red)'; }
    }
  } catch(e){ console.error('Status error',e); }
}

// ─── UTILS ───
function fmt(d){ let m=''+(d.getMonth()+1),y=''+d.getDate(); if(m.length<2)m='0'+m; if(y.length<2)y='0'+y; return [d.getFullYear(),m,y].join('-'); }
function showSection(id){ document.querySelectorAll('.section').forEach(s=>s.classList.remove('active')); document.querySelectorAll('.nav-btn').forEach(b=>b.classList.remove('active')); document.getElementById('sec-'+id).classList.add('active'); document.getElementById('nav-'+id).classList.add('active'); if(id==='backtest') loadBtGames(); if(id==='predict') loadGames(); }
function setDay(m,el){ document.querySelectorAll('#sec-predict .dqb').forEach(b=>b.classList.remove('on')); el.classList.add('on'); const d=new Date(); if(m==='tmrw') d.setDate(d.getDate()+1); sDate=fmt(d); document.getElementById('datepick').value=sDate; loadGames(); }

// ─── GAMES ───
async function loadGames(){
  sDate=document.getElementById('datepick').value||fmt(new Date());
  resetResults();
  const btn=document.getElementById('btn-load'); btn.disabled=true; btn.textContent='Yükleniyor...';
  try {
    const data=await fetch(`${API}/games?date=${sDate}`).then(r=>r.json());
    if(data.error){ alert(data.error); return; }
    const games=data.games||[];
    if(!games.length){ alert(sDate+' tarihinde maç yok.'); return; }
    document.getElementById('games-lbl').textContent = sDate+' · '+games.length+' maç';
    const gh=document.getElementById('games-hint');
    if(gh){
      if(data.hint){ gh.textContent=data.hint; gh.classList.remove('hidden'); }
      else { gh.textContent=''; gh.classList.add('hidden'); }
    }
    const grid=document.getElementById('games-grid'); grid.innerHTML='';
    games.forEach((g,i)=>{
      const el=document.createElement('div'); el.className='game-card';
      el.innerHTML=`<div class="game-num">${String(i+1).padStart(2,'0')}</div><div class="game-away">${g.away}</div><div class="game-vs">@</div><div class="game-home">${g.home}</div>`;
      el.onclick=()=>pickGame(g,el);
      grid.appendChild(el);
    });
    show('sec-games');
  } catch(e) { alert('Hata: '+e.message); }
  finally { btn.disabled=false; btn.textContent='Maçları Getir'; }
}

function pickGame(g, el){
  document.querySelectorAll('.game-card').forEach(c=>c.classList.remove('active'));
  el.classList.add('active');
  sGame=g; sTeam=null;
  hide('sec-predict-btn');
  const row=document.getElementById('team-row'); row.innerHTML='';
  [{id:g.home_id,abbr:g.homeAbbr,name:g.home,sub:'Ev',cls:''},{id:g.away_id,abbr:g.awayAbbr,name:g.away,sub:'Dep',cls:''},{id:'BOTH',abbr:'HER',name:'İki Takım',sub:'Tümü',cls:'both'}].forEach(t=>{
    const btn=document.createElement('div'); btn.className='team-btn'+(t.cls?' '+t.cls:'');
    btn.innerHTML=`<span class="tabbr">${t.abbr}</span><span class="tname">${t.name}</span>`;
    btn.onclick=(function(id){return function(){pickTeam(id,btn);};})(t.id);
    row.appendChild(btn);
  });
  show('sec-team');
}

function pickTeam(id, el){
  document.querySelectorAll('.team-btn').forEach(b=>b.classList.remove('active'));
  el.classList.add('active'); sTeam=id; show('sec-predict-btn');
}

// ─── PREDICT ───
async function runPredict(){
  if(!sGame || !sTeam) return;
  startProg(); hide('sec-games'); hide('sec-team');
  try {
  const use_stake = document.getElementById('chk-stake') ? document.getElementById('chk-stake').checked : false;
    const data = await fetch(`${API}/predict`,{
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({date:sDate,home_id:sGame.home_id,away_id:sGame.away_id,team_id:sTeam, use_stake:use_stake})
    }).then(r=>r.json());
    stopProg();
    if(data.error){ alert(data.error); return; }
    showResults(data, `Takım: ${(sTeam==='BOTH'?'İki Takım':(sTeam==sGame.home_id?sGame.home:sGame.away))}`);
  } catch(e){ stopProg(); alert('Hata: '+e.message); }
}

async function runScan(){
  sDate = document.getElementById('datepick').value || fmt(new Date());
  sGame=null; sTeam=null;
  if(!document.getElementById('games-grid').children.length) await loadGames();
  startProg(); hide('sec-games'); hide('sec-team');
  const use_stake = document.getElementById('chk-stake') ? document.getElementById('chk-stake').checked : false;
  try {
    const data = await fetch(`${API}/scan`,{
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({date:sDate, use_stake:use_stake})
    }).then(r=>r.json());
    stopProg();
    if(data.error){ alert(data.error); return; }
    showResults(data, '🔍 Gece Taraması — '+sDate, data.games_scanned);
  } catch(e){ stopProg(); alert('Hata: '+e.message); }
}

function startProg(){
  hide('sec-results'); show('sec-progress');
  document.getElementById('pfill').style.width='0%';
  document.getElementById('prog-pct').textContent='0%';
  document.getElementById('prog-lbl').textContent='Başlatılıyor...';
  document.getElementById('prog-sub').textContent='';
  _pi = setInterval(()=>{
    fetch(API+'/progress').then(r=>r.json()).then(d=>{
      const p = Math.min(d.pct||0,99);
      document.getElementById('pfill').style.width=p+'%';
      document.getElementById('prog-pct').textContent=p+'%';
      if(d.msg) document.getElementById('prog-lbl').textContent=d.msg;
      if(d.total>0) document.getElementById('prog-sub').textContent=d.done+' / '+d.total+' oyuncu';
    }).catch(()=>{});
  }, 500);
}

function stopProg(){
  clearInterval(_pi);
  document.getElementById('pfill').style.width='100%';
  document.getElementById('prog-pct').textContent='100%';
  setTimeout(()=>hide('sec-progress'),600);
}

// ─── SHOW RESULTS ───
function showResults(data, title, gs){
  allP = data.preds || [];
  currentSgps = data.sgps || [];
  sel.clear();
  if(!allP.length){ alert('Sonuç bulunamadı.'); return; }
  const s = data.summary || {};
  document.getElementById('res-title').textContent = title;
  document.getElementById('res-meta').textContent =
    sDate + (gs?' · '+gs+' maç':'') + ' · '+s.players+' oyuncu' +
    (s.hot_players?' · 🔥'+s.hot_players:'') + (s.cold_players?' · ❄️'+s.cold_players:'');
  const avgEdge = (allP.reduce((s,p)=>s+(p.edge||0),0)/allP.length||0).toFixed(1);
  const rc = s.avg_win_prob>=65?'var(--green)':s.avg_win_prob>=55?'var(--amber)':'var(--red)';
  document.getElementById('res-stats').innerHTML =
    `<div class="sum-box"><span class="sum-val" style="color:var(--blue)">${s.total}</span><span class="sum-lbl">Tahmin</span></div>` +
    `<div class="sum-box"><span class="sum-val" style="color:var(--purple)">${s.players}</span><span class="sum-lbl">Oyuncu</span></div>` +
    `<div class="sum-box"><span class="sum-val" style="color:${rc}">${s.avg_win_prob}%</span><span class="sum-lbl">Kazanma O.</span></div>` +
    `<div class="sum-box"><span class="sum-val" style="color:var(--green)">+${avgEdge}</span><span class="sum-lbl">Ort. Edge</span></div>` +
    `<div class="sum-box"><span class="sum-val" style="color:var(--hot)">${s.hot_players||0}</span><span class="sum-lbl">🔥 HOT</span></div>` +
    `<div class="sum-box"><span class="sum-val" style="color:var(--cold)">${s.cold_players||0}</span><span class="sum-lbl">❄️ COLD</span></div>`;

  // Compare dropdowns güncelle
  const players = [...new Set(allP.map(p=>p.player))].sort();
  ['cmp-p1','cmp-p2'].forEach(id=>{
    const sel2 = document.getElementById(id);
    sel2.innerHTML = '<option value="">Oyuncu seç...</option>';
    players.forEach(p=>{ const opt=document.createElement('option'); opt.value=opt.textContent=p; sel2.appendChild(opt); });
  });

  // Render SGP Panel (HTML olarak oluştur, Render fonksiyonunda göster/gizle)
  const sgpContainer = document.getElementById('sgp-container');
  if(currentSgps.length > 0) {
    let sgpHtml = `<div class="sgp-hdr">🔥 SİSTEM ÖNERİSİ KOMBİNELER <span style="font-weight:400;color:var(--muted);font-size:10px;margin-left:4px">Yapay zeka korelasyon tespitleri</span></div><div class="sgp-grid">`;
    currentSgps.forEach((sgp, idx) => {
        const legsHtml = sgp.legs.map(l => `<div style="display:flex;justify-content:space-between"><span><b>${l.player}</b> <span class="stag ${SCOL[l.stat]||''}">${l.stat}</span> ${l.line!=null?'OVER '+fmtBaremLine(l.line):'TAHMİN'}</span> <span style="color:var(--amber)">${l.has_market_odds&&l.market_odds?l.market_odds.toFixed(2):(l.line!=null?'SIM':'—')}</span></div>`).join('');
        sgpHtml += `<div class="sgp-card">
            <div class="sgp-title">${sgp.title}</div>
            <div class="sgp-desc">${sgp.description}</div>
            <div class="sgp-legs">${legsHtml}</div>
            <div class="sgp-foot">
                <span class="sgp-prob">%${sgp.combined_prob} KAZANMA</span>
                <button class="btn btn-green btn-sm" onclick="addSgpToSlip(${idx})">+ Kupona Ekle</button>
            </div>
        </div>`;
    });
    sgpHtml += `</div>`;
    sgpContainer.innerHTML = sgpHtml;
  } else {
    sgpContainer.innerHTML = '<div style="padding:20px;color:var(--dim);text-align:center">Bu maçlar için güçlü bir korelasyon kombinesi bulunamadı.</div>';
  }

  show('sec-results');
  document.getElementById('btn-csv').style.display='';
  render('ALL');
  updateSlip();
}

// ─── RENDER ───
function render(filter){
  curFilt = filter;
  const body = document.getElementById('results-body');
  const sgpContainer = document.getElementById('sgp-container');
  
  if (filter === 'SGP') {
      body.classList.add('hidden');
      sgpContainer.classList.remove('hidden');
      return;
  }
  
  body.classList.remove('hidden');
  sgpContainer.classList.add('hidden');
  
  body.innerHTML = '';
  let fp = allP;
  if(filter==='HOT') fp=allP.filter(p=>p.trend==='HOT'||p.trend==='WARM');
  else if(filter==='COLD') fp=allP.filter(p=>p.trend==='COLD'||p.trend==='COOLING');
  else if(filter==='VALUE') fp=allP.filter(p=>p.edge>2&&p.win_prob>50);
  else if(filter==='CONF') fp=allP.filter(p=>p.win_prob>=65);
  else if(filter!=='ALL') fp=allP.filter(p=>p.stat===filter);

  const pm={};
  fp.forEach(p=>{
    p._i=allP.indexOf(p);
    if(!pm[p.player]) pm[p.player]={info:p,stats:[]};
    pm[p.player].stats.push(p);
  });

  const players = Object.values(pm).sort((a,b)=>{
    // v12.9: Absolute Perfection - Default Sort by Highest EV
    const maxEvA = Math.max(...a.stats.map(s => s.ev || 0));
    const maxEvB = Math.max(...b.stats.map(s => s.ev || 0));
    if (maxEvB !== maxEvA) return maxEvB - maxEvA;
    
    // Fallback to Win Prob
    const maxWpA = Math.max(...a.stats.map(s => s.win_prob || 0));
    const maxWpB = Math.max(...b.stats.map(s => s.win_prob || 0));
    return maxWpB - maxWpA;
  });

  players.forEach(({info,stats})=>{
    const hasS = stats.some(s=>sel.has(s._i));
    const key = info.player.replace(/[\s.']/g,'_');
    const av = (info.player.split(' ')[0]?.[0]||'')+(info.player.split(' ')[1]?.[0]||'');
    const b2b = info.b2b?'<span class="badge b-b2b">B2B</span>':'';
    const blw = info.blowout?`<span class="badge b-blow">${info.underdog?'🐶':'🏆'}</span>`:'';
    const trendBadge = info.trend==='HOT'?'<span class="badge b-hot">🔥 HOT</span>':
                       info.trend==='COLD'?'<span class="badge b-cold">❄️ COLD</span>':'';
    const anyLive = stats.some(s=>s.has_market_odds);
    const anyBarem = stats.some(s=>s.line!=null && s.line!==undefined);
    const odTag = anyLive
      ? '<span class="odds-indicator">LIVE</span>'
      : (anyBarem ? '<span class="odds-indicator odds-missing">SIM</span>' : '<span class="odds-indicator odds-missing" style="opacity:.9">TAHMİN</span>');
    const maxEdge = Math.max(...stats.map(s=>s.edge||0));
    const edgeClass = maxEdge>2?'value-high':maxEdge>1?'value-med':'value-low';
    
    // v13.0: AI Insights extraction
    const firstStat = stats[0] || {};
    const insights = (firstStat.insights || []).map(i => 
      `<span class="ph-top" style="background:var(--s3);color:var(--blue);margin-right:4px">${i}</span>`
    ).join('');

    // ── Odds panel: bu oyuncunun gerçek market verisi olan statları ──
    const liveStats = stats.filter(s=>s.has_market_odds && s.all_lines && Object.keys(s.all_lines).length>0);
    let oddsHtml = '';
    if(liveStats.length>0){
      const rows = liveStats.map(s=>{
        const pills = Object.entries(s.all_lines)
          .map(([bk,ln])=>`<span class="bk-pill"><span class="bk-name">${bk.toUpperCase()}</span><span class="bk-val">${ln}</span></span>`)
          .join('');
        const dc=s.edge>0?'var(--green)':'var(--red)';
        const impliedPct = s.market_odds ? ((1/s.market_odds)*100).toFixed(0)+'%' : '';
        return `<div class="odds-row">
          <span class="stag ${SCOL[s.stat]||''}" style="font-size:8px;margin-right:6px;flex-shrink:0">${s.stat}</span>
          <div class="bk-pills">${pills}</div>
          <div style="margin-left:auto;padding-right:14px;text-align:right;flex-shrink:0">
            <span style="font-family:var(--mono);font-size:10px;color:${dc}">${s.edge>0?'+':''}${s.edge.toFixed(1)}</span>
            <span style="font-family:var(--mono);font-size:9px;color:var(--amber);margin-left:6px">${s.best_bookmaker} ${s.market_odds?s.market_odds.toFixed(2):''}</span>
            ${impliedPct?`<span style="font-family:var(--mono);font-size:8px;color:var(--muted);margin-left:4px">(imp. ${impliedPct})</span>`:''}
          </div>
        </div>`;
      }).join('');
      oddsHtml = `<div class="odds-panel">
        <div class="odds-panel-hdr">📊 Market Lines — ${liveStats.length} prop</div>
        ${rows}
      </div>`;
    }

    const block = document.createElement('div');
    block.className = 'player-block fup'+(hasS?' has-sel':'');
    block.id = 'pb_'+key;
    block.innerHTML =
      `<div class="player-head" onclick="togBlock('${key}',this)">
        <div class="ph-av">${av}</div>
        <div class="ph-info">
          <div class="ph-name">${info.player}${odTag}</div>
          <div class="ph-sub">${info.team} vs ${info.opp} · ${info.position||'-'}</div>
        </div>
        <div class="ph-right">${insights}${b2b}${blw}${trendBadge}<span class="ph-cnt">${stats.length} stat</span><span class="ph-top ${edgeClass}">+${maxEdge.toFixed(1)}</span></div>
        <span class="ph-arr open" id="arr_${key}">▾</span>
      </div>
      <div class="stat-rows" id="sr_${key}">
        <div class="stat-hr"><span></span><span>STAT</span><span>YÖN/BAREM</span><span style="text-align:right">EV</span><span style="text-align:right">EDGE</span><span style="text-align:right">TAHMİN</span><span style="text-align:right">RANGE</span><span style="text-align:right">KAZANMA O.</span><span style="text-align:right">KELLY Ö.</span></div>
        <div id="srl_${key}"></div>
        ${oddsHtml}
      </div>`;
    body.appendChild(block);

    const list = document.getElementById('srl_'+key);
    stats.sort((a,b)=>SORD.indexOf(a.stat)-SORD.indexOf(b.stat));
    stats.forEach(p=>{
      const sc=SCOL[p.stat]||'';
      const diff=p.edge;
      const dc=diff>0?'var(--green)':diff<0?'var(--red)':'var(--muted)';
      const ds=(diff>0?'+':'')+diff.toFixed(1);
      const wp = p.win_prob || 0;
      const rc = wp >= 65 ? 'var(--green)' : wp >= 55 ? 'var(--amber)' : 'var(--red)';
      
      let bankroll = parseFloat(document.getElementById('bankroll')?.value) || 1000;
      let kellyTL = (bankroll * (p.kelly || 0) / 100).toFixed(0) + ' ₺';
      if(p.kelly <= 0) kellyTL = '-';
      // Bookmaker + odds — gerçek veri varsa renkli göster
      const bmk=p.has_market_odds&&p.best_bookmaker
        ?`<span class="bmk-tag" style="color:var(--green)">${p.best_bookmaker} ${p.market_odds?p.market_odds.toFixed(2):''}</span>`
        :(p.line!=null&&p.line!==undefined?`<span class="bmk-tag">SIM</span>`:`<span class="bmk-tag" style="color:var(--muted)">—</span>`);
      const tl=p.trend_label?`<span style="font-size:10px;margin-left:2px">${p.trend_label}</span>`:'';
      const ck=sel.has(p._i);
      const dr=p.is_danger?'<span class="is-danger-icon" title="Tuzak Barem Uyarısı: Market ile model arasında çok büyük fark var! ( >%25)">⚠️</span>':'';
      const out_tag=(p.line==null||p.line===undefined)
        ?`<span class="outcome-tag" style="color:var(--muted);font-size:9px">TAHMİN</span>`
        :`<span class="outcome-tag ${p.expected_outcome==='OVER'?'over':'under'}">${p.expected_outcome==='OVER'?'ÜST':'ALT'}</span>`;
      const ev_val=(p.ev||0);
      const ev_c=ev_val>0?'var(--green)':ev_val<0?'var(--red)':'var(--muted)';
      const row=document.createElement('div');
      row.className='stat-row'+(ck?' ck':'');
      row.dataset.i=p._i;
      row.onclick=()=>togSel(p._i);
      row.innerHTML=`<input class="sr-chk" type="checkbox"${ck?' checked':''} onclick="event.stopPropagation();togSel(${p._i})">
        <span class="stag ${sc}">${p.stat}</span>
        <div class="barem-wrap">${out_tag}<span class="barem-val">${fmtBarem(p)}</span>${dr}${bmk}${tl}</div>
        <div class="ev-cell" style="color:${ev_c}">${(ev_val>0?'+':'')+ev_val.toFixed(2)}</div>
        <div class="diff-cell" style="color:${dc}">${ds}</div>
        <div class="pred-cell" style="color:${rc}">${p.pred.toFixed(1)}</div>
        <div class="range-cell">${p.floor.toFixed(1)}–${p.ceiling.toFixed(1)}</div>
        <div class="risk-wrap"><div class="risk-track"><div class="risk-fill" style="width:${wp}%;background:${rc}"></div></div><span class="risk-num" style="color:${rc}">%${wp.toFixed(1)}</span></div>
        <span class="conf-cell" style="color:var(--bg);background:${p.kelly>0?'var(--green)':'var(--s3)'}">${kellyTL}</span>`;
      list.appendChild(row);
    });
  });
  syncChk();
}

function filtTrend(trend,el){ document.querySelectorAll('.ftab').forEach(b=>b.classList.remove('on')); el.classList.add('on'); render(trend); }
function filt(s,el){ document.querySelectorAll('.ftab').forEach(b=>b.classList.remove('on')); el.classList.add('on'); render(s); }
function togBlock(key,h){ const b=document.getElementById('sr_'+key); const a=document.getElementById('arr_'+key); if(!b)return; const op=!b.classList.contains('hidden'); b.classList.toggle('hidden',op); if(a)a.classList.toggle('open',!op); }

// ─── SGP SLIP ADD ───
function addSgpToSlip(idx) {
    const sgp = currentSgps[idx];
    if(!sgp) return;
    let added = 0;
    sgp.legs.forEach(leg => {
        const pIdx = allP.findIndex(p => p.player === leg.player && p.stat === leg.stat);
        if(pIdx !== -1 && !sel.has(pIdx)) {
            sel.add(pIdx);
            document.querySelectorAll(`.stat-row[data-i="${pIdx}"]`).forEach(c=>{
              c.classList.add('ck');
              const ch=c.querySelector('.sr-chk'); if(ch) ch.checked=true;
            });
            added++;
        }
    });
    if(added > 0) {
        updateSlip(); 
        syncChk();
        const badge=document.getElementById('slip-badge');
        badge.style.transform='scale(1.2)';
        setTimeout(()=>badge.style.transform='none', 200);
    }
}

// ─── SELECTION ───
function togSel(i){
  if(sel.has(i)) sel.delete(i); else sel.add(i);
  document.querySelectorAll(`.stat-row[data-i="${i}"]`).forEach(c=>{
    c.classList.toggle('ck',sel.has(i));
    const ch=c.querySelector('.sr-chk'); if(ch) ch.checked=sel.has(i);
  });
  updateSlip(); syncChk();
}
function toggleAll(m){
  const vis=getVis();
  if(m.checked) vis.forEach(i=>sel.add(i)); else vis.forEach(i=>sel.delete(i));
  document.querySelectorAll('.stat-row').forEach(c=>{
    const i=parseInt(c.dataset.i); c.classList.toggle('ck',sel.has(i));
    const ch=c.querySelector('.sr-chk'); if(ch) ch.checked=sel.has(i);
  });
  updateSlip(); syncChk();
}
function getVis(){ return Array.from(document.querySelectorAll('.stat-row')).map(r=>parseInt(r.dataset.i)).filter(i=>!isNaN(i)); }
function syncChk(){
  const vis=getVis();
  const m=document.getElementById('chk-all'); if(m) m.checked=vis.length>0&&vis.every(i=>sel.has(i));
  const c=document.getElementById('sel-cnt'); if(c) c.textContent=sel.size+' seçili';
}

// ─── SLIP ───
function updateSlip(){
  const items=Array.from(sel).map(i=>allP[i]).filter(x=>x);
  const badge=document.getElementById('slip-badge'); if(badge) badge.textContent=items.length+' seçim';
  const emp=document.getElementById('slip-empty'),lst=document.getElementById('slip-list'),foot=document.getElementById('slip-foot');
  if(!items.length){ emp.classList.remove('hidden'); lst.classList.add('hidden'); foot.classList.add('hidden'); return; }
  emp.classList.add('hidden'); lst.classList.remove('hidden'); foot.classList.remove('hidden');
  lst.innerHTML='';
  items.forEach(p=>{
    const dc=p.edge>0?'var(--green)':p.edge<0?'var(--red)':'var(--muted)';
    const ds=(p.edge>0?'+':'')+p.edge.toFixed(1);
    const sc=SCOL[p.stat]||'';
    const tl=p.trend_label?` ${p.trend_label}`:'';
    const oddsInfo=p.has_market_odds?`<span style="color:var(--amber);font-size:8px">${p.best_bookmaker} ${p.market_odds?p.market_odds.toFixed(2):''}</span> `:'';
    const el=document.createElement('div'); el.className='slip-item';
    const out_txt=(p.line==null||p.line===undefined)?'TAHMİN':(p.expected_outcome==='OVER'?'ÜST':'ALT');
    const baremLbl=(p.line==null||p.line===undefined)?'':(' '+fmtBarem(p));
    el.innerHTML=`<div class="si-info"><div class="si-name">${p.player}${tl}</div><div class="si-det"><span class="stag ${sc}" style="padding:1px 4px;font-size:8px">${p.stat}</span> <b>${out_txt}${baremLbl}</b> ${oddsInfo}<span style="color:${dc}">${ds}</span></div></div><div class="si-right"><div class="si-pred">${p.pred.toFixed(1)}</div><div class="si-conf">%${p.win_prob}</div></div><button class="si-rm" onclick="rmSel(${allP.indexOf(p)})">×</button>`;
    lst.appendChild(el);
  });
  const ae=items.reduce((s,p)=>s+(p.edge||0),0)/items.length;
  const aw = items.reduce((s,p)=>s+(p.win_prob||0),0)/items.length;
  document.getElementById('sf-n').textContent=items.length;
  document.getElementById('sf-edge').textContent=(ae>0?'+':'')+ae.toFixed(1);
  document.getElementById('sf-edge').style.color=ae>0?'var(--green)':'var(--red)';
  document.getElementById('sf-conf').textContent='%'+aw.toFixed(1);
}
function rmSel(i){ sel.delete(i); document.querySelectorAll(`.stat-row[data-i="${i}"]`).forEach(c=>{ c.classList.remove('ck'); const ch=c.querySelector('.sr-chk'); if(ch) ch.checked=false; }); updateSlip(); syncChk(); }
function clearSlip(){ sel.clear(); document.querySelectorAll('.stat-row').forEach(c=>{ c.classList.remove('ck'); const ch=c.querySelector('.sr-chk'); if(ch) ch.checked=false; }); updateSlip(); syncChk(); }

async function saveSlip(){
  const items=Array.from(sel).map(i=>allP[i]).filter(x=>x); if(!items.length) return;
  const defN=(sGame?sGame.awayAbbr+'@'+sGame.homeAbbr:'Tarama')+' — '+sDate;
  const name=prompt('Kupon adı:',defN); if(name===null) return;
  const btn=document.querySelector('.slip-save'); btn.disabled=true; btn.textContent='⏳ Kaydediliyor...';
  try {
    const data=await fetch(`${API}/save_slip`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preds:items,name:name||defN,date:sDate})}).then(r=>r.json());
    if(data.error){ alert('Hata: '+data.error); return; }
    btn.textContent='✓ Kaydedildi!'; btn.style.background='var(--green)';
    setTimeout(()=>{ btn.disabled=false; btn.textContent='💾 Kuponu Kaydet'; btn.style.background=''; },2500);
    loadHist(); showModal(items,name||defN,data.slip_id);
  } catch(e){ alert('Hata: '+e.message); btn.disabled=false; btn.textContent='💾 Kuponu Kaydet'; }
}

async function loadHitRates(){
  try {
    const data=await fetch(`${API}/backtest/history`).then(r=>r.json());
    const tbody=document.getElementById('hr-tbody'); if(!tbody) return;
    const hr=data.hit_rates||[];
    if(!hr.length){ tbody.innerHTML='<tr><td colspan="4" style="color:var(--dim);text-align:center;padding:12px">Henüz backtest verisi yok</td></tr>'; return; }
    tbody.innerHTML=hr.map(r=>{
      const c=r.hit_rate>=0.6?'var(--green)':r.hit_rate>=0.5?'var(--amber)':'var(--red)';
      return `<tr><td>${r.stat}</td><td style="color:${c};font-weight:700">${(r.hit_rate*100).toFixed(1)}%</td><td>${r.avg_error}</td><td>${r.total}</td></tr>`;
    }).join('');
  } catch(e){ console.error('loadHitRates error',e); }
}

// ─── COMPARE ───
async function runCompare(){
  const p1=document.getElementById('cmp-p1').value;
  const p2=document.getElementById('cmp-p2').value;
  if(!p1||!p2||p1===p2){ alert('İki farklı oyuncu seçin'); return; }
  try {
    const data=await fetch(`${API}/compare`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({player1:p1,player2:p2,preds:allP})}).then(r=>r.json());
    if(data.error){ alert(data.error); return; }
    const grid=document.getElementById('cmp-grid'); grid.innerHTML='';
    [data.player1,data.player2].forEach(pd=>{
      const card=document.createElement('div'); card.className='cmp-card';
      const stats=pd.stats||{};
      const statRows=Object.entries(stats).sort((a,b)=>SORD.indexOf(a[0])-SORD.indexOf(b[0])).map(([stat,s])=>{
        const dc=s.edge>0?'var(--green)':s.edge<0?'var(--red)':'var(--muted)';
        const tl=s.trend_label||'';
        return `<div class="cmp-row"><span class="stag ${SCOL[stat]||''}" style="font-size:8px">${stat}</span><div><span class="cmp-val">${s.pred.toFixed(1)}</span><span style="font-family:var(--mono);font-size:8px;color:${dc};margin-left:4px">${s.edge>0?'+':''}${s.edge.toFixed(1)}</span><span style="margin-left:4px">${tl}</span></div><span style="font-family:var(--mono);font-size:9px;color:var(--muted)">%${s.win_prob}</span></div>`;
      }).join('');
      card.innerHTML=`<div class="cmp-name">${pd.name}</div>${statRows}`;
      grid.appendChild(card);
    });
    document.getElementById('cmp-results').classList.remove('hidden');
  } catch(e){ alert('Hata: '+e.message); }
}

// ─── CSV EXPORT ───
async function exportCSV(){
  if(!allP.length){ alert('Önce tahmin çalıştırın'); return; }
  const btn=document.getElementById('btn-csv'); btn.disabled=true; btn.textContent='⏳';
  try {
    const resp=await fetch(`${API}/export/csv`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({preds:allP})});
    const blob=await resp.blob();
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a'); a.href=url; a.download=`nba_preds_${sDate}.csv`; a.click();
    URL.revokeObjectURL(url);
  } catch(e){ alert('Export hatası: '+e.message); }
  finally { btn.disabled=false; btn.textContent='⬇️ CSV'; }
}

// ─── ODDS ───
async function refreshOdds(){
  const btn=document.getElementById('btn-odds'); btn.disabled=true; btn.textContent='⏳';
  try {
    const data=await fetch(`${API}/odds/${sDate}`).then(r=>r.json());
    if(data.error) alert('Odds hatası: '+data.error);
    else alert(`${data.players_with_props} oyuncu için odds güncellendi!`);
  } catch(e){ alert('Hata: '+e.message); }
  finally { btn.disabled=false; btn.textContent='🔄 Odds'; }
}

// ─── SETTINGS ───
async function saveSettings(){
  const key=document.getElementById('settings-odds-key').value;
  if(!key){ alert('API Key girin'); return; }
  const r=await fetch(`${API}/config`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({odds_api_key:key})}).then(r=>r.json());
  if(r.status==='saved'){
    const s=document.getElementById('settings-status'); s.style.display='block';
    setTimeout(()=>s.style.display='none',2500);
    checkStatus();
  }
}

// ─── HISTORY & INJURIES ───
async function loadHist(){
  try {
    const data=await fetch(`${API}/slips`).then(r=>r.json());
    const el=document.getElementById('hist-body'); if(!el) return;
    const slips=data.slips||[];
    if(!slips.length){ el.innerHTML='<div style="padding:12px;font-family:var(--mono);font-size:9px;color:var(--dim)">Henüz kupon yok</div>'; return; }
    el.innerHTML=slips.map(s=>{
      const c=s.avg_edge>=0?'var(--green)':'var(--red)';
      return `<div class="hist-item"><div class="hi-info"><div class="hi-name">${s.ad||'—'}</div><div class="hi-meta">${s.tarih} · ${s.secim} seçim</div></div><div class="hi-edge" style="color:${c}">${s.avg_edge>=0?'+':''}${s.avg_edge?.toFixed(1)}</div></div>`;
    }).join('');
  } catch(e){ console.error('loadHist error',e); }
}

async function loadInjuries(){
  try {
    const data=await fetch(`${API}/injuries`).then(r=>r.json());
    const outEl=document.getElementById('inj-out'), questEl=document.getElementById('inj-quest');
    const out=data.out||{}, q=data.questionable||{};
    outEl.innerHTML=Object.keys(out).length?Object.entries(out).slice(0,5).map(([n,s])=>`<div>${n}: <span style="color:var(--red)">${s}</span></div>`).join('')+(Object.keys(out).length>5?`<div style="color:var(--dim)">+${Object.keys(out).length-5} daha</div>`:''):'<span style="color:var(--dim)">Yok</span>';
    questEl.innerHTML=Object.keys(q).length?Object.entries(q).slice(0,3).map(([n,s])=>`<div>${n}: <span style="color:var(--amber)">${s}</span></div>`).join(''):'<span style="color:var(--dim)">Yok</span>';
  } catch(e){ console.error('loadInjuries error',e); }
}

// ─── MODAL ───
function showModal(items,name,sid){
  let html='';
  items.forEach((p,i)=>{
    const dc=p.edge>0?'var(--green)':p.edge<0?'var(--red)':'var(--muted)';
    const sc=SCOL[p.stat]||'';
    html+=`<div class="exp-item"><span class="exp-num">${i+1}</span><div style="flex:1;min-width:0"><div class="exp-player">${p.player}</div><div style="font-family:var(--mono);font-size:8px;color:var(--muted)">${p.team} vs ${p.opp}</div></div><span class="stag ${sc}" style="padding:1px 5px;font-size:8px">${p.stat}</span><div class="exp-right"><div class="exp-over">${p.line!=null?'OVER '+fmtBarem(p):'TAHMİN'}</div><div class="exp-diff" style="color:${dc}">${p.edge>0?'+':''}${p.edge.toFixed(1)}</div></div></div>`;
  });
  document.getElementById('modal-items').innerHTML=html;
  const ae=items.reduce((s,p)=>s+(p.edge||0),0)/items.length;
  const ac=items.reduce((s,p)=>s+(p.win_prob||0),0)/items.length;
  document.getElementById('modal-sum').innerHTML=
    `<span style="color:var(--text)">Kupon:</span> ${name}<br><span style="color:var(--text)">Seçim:</span> ${items.length}<br><span style="color:var(--text)">Ort. Edge:</span> <span style="color:${ae>0?'var(--green)':'var(--red)'}">${ae>0?'+':''}${ae.toFixed(1)}</span><br><span style="color:var(--text)">Ort. Güven:</span> %${ac.toFixed(1)}<br><span style="color:var(--green)">✓ Kaydedildi (ID:${sid})</span>`;
  document.getElementById('modal').classList.remove('hidden');
}

function closeModal(){ document.getElementById('modal').classList.add('hidden'); }

function copySlip(){
  const items=Array.from(sel).map(i=>allP[i]).filter(x=>x);
  const txt=items.map((p,i)=>`${i+1}. ${p.player} | ${p.stat} ${p.line!=null?'OVER '+fmtBarem(p):'TAHMİN '+p.pred.toFixed(1)} | Edge:${p.edge>0?'+':''}${p.edge.toFixed(1)} | Tahmin:${p.pred.toFixed(1)}${p.trend_label?' '+p.trend_label:''}`).join('\n');
  navigator.clipboard.writeText(`NBA Predictor v12 — ${sDate}\n${'─'.repeat(44)}\n${txt}`).then(()=>{
    const b=document.querySelector('.copy-btn'); b.textContent='✓ Kopyalandı!'; setTimeout(()=>b.textContent='📋 Kopyala',2000);
  });
}

// ─── UTILS ───
function togPanel(bId,aId){ const b=document.getElementById(bId),a=document.getElementById(aId); const op=!b.classList.contains('hidden'); b.classList.toggle('hidden',op); if(a) a.textContent=op?'▶':'▼'; }
function show(id){ const e=document.getElementById(id); if(e){ e.classList.remove('hidden'); e.classList.add('fup'); } }
function hide(id){ const e=document.getElementById(id); if(e) e.classList.add('hidden'); }
function resetResults(){ hide('sec-results'); hide('sec-team'); hide('sec-predict-btn'); hide('sec-progress'); document.querySelectorAll('.game-card').forEach(c=>c.classList.remove('active')); sGame=null; sTeam=null; allP=[]; currentSgps=[]; sel.clear(); document.getElementById('btn-csv').style.display='none'; document.getElementById('pfill').style.width='0%'; const grid=document.getElementById('games-grid'); if(grid&&grid.children.length>0) show('sec-games'); updateSlip(); }

// ─── BACKTEST GAME/TEAM PICKER ───
let btDate='', btGame=null, btTeam=null, _btPi=null;

function setBtDay(m,el){
  document.querySelectorAll('#sec-backtest .dqb').forEach(b=>b.classList.remove('on')); el.classList.add('on');
  const d=new Date();
  if(m==='yest') d.setDate(d.getDate()-1);
  btDate=fmt(d); document.getElementById('bt-datepick').value=btDate;
}

async function loadBtGames(){
  btDate=document.getElementById('bt-datepick').value||fmt(new Date());
  const btn=document.getElementById('btn-bt-load'); btn.disabled=true; btn.textContent='Yükleniyor...';
  try{
    const data=await fetch(`${API}/games?date=${btDate}`).then(r=>r.json());
    if(data.error){alert(data.error);return;}
    const games=data.games||[];
    if(!games.length){alert(btDate+' tarihinde maç yok.');return;}
    document.getElementById('bt-games-lbl').textContent=btDate+' · '+games.length+' maç';
    const grid=document.getElementById('bt-games-grid'); grid.innerHTML='';
    games.forEach((g,i)=>{
      const el=document.createElement('div'); el.className='game-card';
      el.innerHTML=`<div class="game-num">${String(i+1).padStart(2,'0')}</div><div class="game-away">${g.away}</div><div class="game-vs">@</div><div class="game-home">${g.home}</div>`;
      el.onclick=()=>pickBtGame(g,el);
      grid.appendChild(el);
    });
    show('bt-games-wrap'); hide('bt-team-wrap'); hide('bt-run-wrap'); hide('bt-results');
  }catch(e){alert('Hata: '+e.message);}
  finally{btn.disabled=false; btn.textContent='Maçları Getir';}
}

function pickBtGame(g,el){
  document.querySelectorAll('#bt-games-grid .game-card').forEach(c=>c.classList.remove('active'));
  el.classList.add('active'); btGame=g; btTeam=null;
  const row=document.getElementById('bt-team-row'); row.innerHTML='';
  [{id:g.home_id,abbr:g.homeAbbr,name:g.home,sub:'Ev',cls:''},{id:g.away_id,abbr:g.awayAbbr,name:g.away,sub:'Dep',cls:''},{id:'BOTH',abbr:'HER',name:'İki Takım',sub:'Tümü',cls:'both'}].forEach(t=>{
    const btn=document.createElement('div'); btn.className='team-btn'+(t.cls?' '+t.cls:'');
    btn.innerHTML=`<span class="tabbr">${t.abbr}</span><span class="tname">${t.name}</span>`;
    btn.onclick=(function(id){return function(){pickBtTeam(id,btn);};})(t.id);
    row.appendChild(btn);
  });
  show('bt-team-wrap'); hide('bt-run-wrap');
}

function pickBtTeam(id,el){
  document.querySelectorAll('#bt-team-row .team-btn').forEach(b=>b.classList.remove('active'));
  el.classList.add('active'); btTeam=id; show('bt-run-wrap');
}

async function runBtGame(){
  if(!btGame||!btTeam) return;
  startBtProg();
  try{
    const data=await fetch(`${API}/backtest`,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({date:btDate,home_id:btGame.home_id,away_id:btGame.away_id,team_id:btTeam})
    }).then(r=>r.json());
    stopBtProg(); if(data.error){alert(data.error);return;}
    showBtResults(data);
  }catch(e){stopBtProg();alert('Hata: '+e.message);}
}

async function runBtAll(){
  btDate=document.getElementById('bt-datepick').value||fmt(new Date());
  startBtProg();
  try{
    const data=await fetch(`${API}/backtest`,{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({date:btDate})
    }).then(r=>r.json());
    stopBtProg(); if(data.error){alert(data.error);return;}
    showBtResults(data);
  }catch(e){stopBtProg();alert('Hata: '+e.message);}
}

function startBtProg(){
  hide('bt-results'); show('bt-progress');
  document.getElementById('bt-pfill').style.width='0%';
  _btPi=setInterval(()=>{
    fetch(API+'/progress').then(r=>r.json()).then(d=>{
      const p=Math.min(d.pct||0,99);
      document.getElementById('bt-pfill').style.width=p+'%';
      document.getElementById('bt-prog-pct').textContent=p+'%';
      if(d.msg) document.getElementById('bt-prog-lbl').textContent=d.msg;
      if(d.total>0) document.getElementById('bt-prog-sub').textContent=d.done+'/'+d.total+' oyuncu';
    }).catch(()=>{});
  },600);
}

function stopBtProg(){
  clearInterval(_btPi);
  document.getElementById('bt-pfill').style.width='100%';
  setTimeout(()=>hide('bt-progress'),500);
}

function showBtResults(data){
  document.getElementById('bt-results').classList.remove('hidden');
  document.getElementById('bt-total').textContent=data.total_predictions;
  document.getElementById('bt-verified').textContent=data.verified;
  const wrc=data.win_rate>=55?'var(--green)':data.win_rate>=50?'var(--amber)':'var(--red)';
  document.getElementById('bt-winrate').textContent=data.win_rate+'%';
  document.getElementById('bt-winrate').style.color=wrc;
  const rc=data.roi_sim>=0?'var(--green)':'var(--red)';
  document.getElementById('bt-roi').textContent=(data.roi_sim>=0?'+':'')+data.roi_sim+'%';
  document.getElementById('bt-roi').style.color=rc;
  document.getElementById('bt-avgerr').textContent=data.avg_error;
  document.getElementById('bt-avgconf').textContent=data.avg_conf+'%';
  document.getElementById('bt-hits').textContent=(data.hits||0)+'/'+(data.verified||0);
  document.getElementById('bt-avgedge').textContent=(data.avg_edge>=0?'+':'')+data.avg_edge;

  const tbody=document.getElementById('bt-tbody'); tbody.innerHTML='';
  (data.predictions||[]).forEach(p=>{
    const hitCls=p.hit===1?'hit-yes':p.hit===0?'hit-no':p.hit===null?'hit-push':'hit-unknown';
    const hitTxt=p.hit===1?'✓ HIT':p.hit===0?'✗ MISS':p.hit===null?'İADE':'?';
    const tl=p.trend_label||'';
    const oddsCell=p.has_market_odds
      ?`<span style="color:var(--green);font-family:var(--mono);font-size:9px">${p.best_bookmaker} ${p.market_odds?p.market_odds.toFixed(2):''}</span>`
      :'<span style="color:var(--dim);font-size:9px">SIM</span>';
    const tr=document.createElement('tr');
    tr.innerHTML=`<td><strong>${p.player}</strong>${tl?` <span>${tl}</span>`:''}</td><td>${p.team}</td><td>${p.stat}</td><td>${p.predicted}</td><td style="font-weight:700">${p.actual!==null?p.actual:'?'}</td><td>${p.line}</td><td>${p.abs_error!==null&&p.abs_error!==undefined?p.abs_error:'?'}</td><td class="${hitCls}" style="font-weight:700">${hitTxt}</td><td>%${p.conf}</td><td>${oddsCell}</td>`;
    tbody.appendChild(tr);
  });
  loadHitRates();
}
