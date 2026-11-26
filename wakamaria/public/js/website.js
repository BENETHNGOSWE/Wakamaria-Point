(() => {
  const defaultImage = 'data:image/svg+xml,' + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><path fill="#cbe2cd" d="M32 3 55 11v18c0 15-9 25-23 32C18 54 9 44 9 29V11z"/><path fill="#216e4f" d="M32 8 50 14v15c0 11-6 19-18 26-12-7-18-15-18-26V14z"/><circle cx="32" cy="29" r="14" fill="#f7fbf5"/><path d="m32 19 5 4-2 6h-6l-2-6zm-11 6 5-2m-5 2 1 7 5 3 2-6m14-4-5-2m5 2-1 7-5 3-2-6m-8 6 2 5h6l2-5" fill="none" stroke="#216e4f" stroke-width="2" stroke-linejoin="round"/></svg>`);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let leagues=[], matches=[], selectedLeague='All leagues', selectedStatus='all', selectedDate='All dates', search='', siteTimezone='';
  const tipText={'1':'Home win','X':'Draw','2':'Away win','1X':'Home win or draw','X2':'Draw or away win','12':'Either team wins','Over 1.5':'2 or more goals','Over 2.5':'3 or more goals','Over 3.5':'4 or more goals','Over 4.5':'5 or more goals','Under 1.5':'0 or 1 goal','Under 2.5':'Fewer than 3 goals','Under 3.5':'Fewer than 4 goals','Under 4.5':'4 or fewer goals','BTTS Yes':'Both teams score','BTTS No':'At least one team does not score','Home Over 1.5':'Home team scores 2 or more','Away Over 1.5':'Away team scores 2 or more','1 & BTTS Yes':'Home win and both teams score'}
  const fmtOdds = v => { const n = Number(v); return Number.isFinite(n) && n > 0 ? n.toFixed(2) : '—'; };
  const dateParts = input => { const [day='',time=''] = String(input||'').split(/[ T]/); return {day,time:time.slice(0,5)}; };
  const safeImage = path => typeof path==='string' && /^\/(files|assets)\//.test(path) ? path : defaultImage;
  const image = l => `<img src="${esc(safeImage(l.league_image))}" alt="" data-league-image>`;
  function badge(m) { let o=m.result_confirmed && ['Win','Lose'].includes(m.outcome) ? m.outcome : 'Pending'; let cls=o==='Win'?'correct':o==='Lose'?'incorrect':'pending'; return `<span class="outcome ${cls}">${o==='Win'?'✓ Win':o==='Lose'?'✕ Lose':'◷ Pending'}</span>`; }
  function siteNow() {
    try { return new Intl.DateTimeFormat('sv-SE', {timeZone:siteTimezone || 'UTC', year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit', hourCycle:'h23'}).format(new Date()).replace(' ', 'T'); }
    catch (_) { return new Date().toISOString().slice(0,19); }
  }
  function inSelectedStatus(m, now) {
    if (selectedStatus==='finished') return Boolean(m.result_confirmed);
    if (m.result_confirmed) return false;
    if (selectedStatus==='upcoming') return String(m.kickoff||'').replace(' ', 'T') > now;
    return true; // All matches means all results still awaiting confirmation.
  }
  function leagueButtons(statusMatches) {
    let html=leagues.map(l=>`<button class="side-btn ${selectedLeague===l.name?'active':''}" data-league="${esc(l.name)}"><span class="side-ic">${image(l)}</span>${esc(l.league_name)} <span class="count">${statusMatches.filter(m=>m.league===l.name).length}</span></button>`).join('');
    document.getElementById('side-leagues').innerHTML=html;
    document.getElementById('mobile-leagues').innerHTML=`<button class="side-btn ${selectedLeague==='All leagues'?'active':''}" data-league="All leagues">All leagues</button>`+html;
    document.querySelector('.sidebar [data-league="All leagues"]').classList.toggle('active',selectedLeague==='All leagues');document.getElementById('all-count').textContent=statusMatches.length;
  }
  const dayKey = value => String(value || '').slice(0, 10);
  function dateLabel(key) {
    const today = dayKey(siteNow());
    const diff = Math.round((new Date(key+'T00:00:00') - new Date(today+'T00:00:00')) / 86400000);
    if (diff === 0) return 'Today';
    if (diff === 1) return 'Tomorrow';
    if (diff === -1) return 'Yesterday';
    try {
      return new Date(key+'T00:00:00').toLocaleDateString('en-GB', {weekday:'short', day:'numeric', month:'short'});
    } catch (_) { return key; }
  }
  let dayCounts = {}, calMonth = null;
  const pad2 = n => String(n).padStart(2, '0');
  const FUTURE_DAYS = 2;   // past is always open; forward stops here

  const keyOf = d => `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  function maxSelectableKey() {
    const base = new Date(dayKey(siteNow()) + 'T00:00:00');
    base.setDate(base.getDate() + FUTURE_DAYS);
    return keyOf(base);
  }

  function updateDateTrigger() {
    // Counts come from every match, so the dots do not move when you change tab:
    // a past date must stay reachable from Finished whether or not the pending
    // view happens to hold anything.
    const maxKey = maxSelectableKey();
    dayCounts = {};
    matches.forEach(m => {
      const k = dayKey(m.kickoff);
      if (k && k <= maxKey) dayCounts[k] = (dayCounts[k] || 0) + 1;
    });
    if (selectedDate !== 'All dates' && selectedDate > maxKey) selectedDate = 'All dates';
    const label = document.getElementById('date-trigger-label');
    if (label) label.textContent = selectedDate === 'All dates' ? 'All dates' : dateLabel(selectedDate);
    const trigger = document.getElementById('date-trigger');
    if (trigger) trigger.classList.toggle('on', selectedDate !== 'All dates');
  }

  function renderCalendar() {
    const cal = document.getElementById('calendar');
    if (!cal) return;
    const base = calMonth || new Date(dayKey(siteNow()) + 'T00:00:00');
    const year = base.getFullYear(), month = base.getMonth();
    const first = new Date(year, month, 1);
    const lead = (first.getDay() + 6) % 7;              // Monday-first grid
    const days = new Date(year, month + 1, 0).getDate();
    const title = first.toLocaleDateString('en-GB', {month: 'long', year: 'numeric'});
    const maxKey = maxSelectableKey();

    let grid = ['Mo','Tu','We','Th','Fr','Sa','Su']
      .map(d => `<span class="cal-dow">${d}</span>`).join('');
    for (let i = 0; i < lead; i++) grid += '<span></span>';
    for (let d = 1; d <= days; d++) {
      const key = `${year}-${pad2(month + 1)}-${pad2(d)}`;
      const n = dayCounts[key] || 0;
      const open = key <= maxKey;
      const cls = 'cal-day' + (open ? ' open' : '') + (n ? ' has' : '') + (selectedDate === key ? ' sel' : '');
      grid += `<button class="${cls}" data-cal-day="${key}"${open ? '' : ' disabled'}>${d}${n ? '<i class="dot"></i>' : ''}</button>`;
    }

    const withMatches = Object.keys(dayCounts).length;
    cal.innerHTML = `<div class="cal-head">`
      + `<button class="cal-nav" data-cal-nav="-1" aria-label="Previous month">&#8249;</button>`
      + `<span class="cal-title">${esc(title)}</span>`
      + `<button class="cal-nav" data-cal-nav="1" aria-label="Next month">&#8250;</button></div>`
      + `<div class="cal-grid">${grid}</div>`
      + `<div class="cal-foot"><span class="cal-count">${withMatches} date${withMatches === 1 ? '' : 's'} with fixtures</span>`
      + `<button class="cal-clear" data-cal-clear>All dates</button></div>`;
  }

  function toggleCalendar(open) {
    const cal = document.getElementById('calendar');
    const trigger = document.getElementById('date-trigger');
    if (!cal || !trigger) return;
    if (open && !calMonth) {
      calMonth = new Date((selectedDate !== 'All dates' ? selectedDate : dayKey(siteNow())) + 'T00:00:00');
    }
    cal.hidden = !open;
    trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) renderCalendar();
  }

  function shiftMonth(delta) {
    const base = calMonth || new Date(dayKey(siteNow()) + 'T00:00:00');
    calMonth = new Date(base.getFullYear(), base.getMonth() + delta, 1);
    renderCalendar();
  }

  // Ben Rule and Grace Rule ride on the same fixture, so the list can show
  // whichever you ask for without changing a single match row. Swapping the
  // fields up front keeps the renderer unaware there are two rules at all.
  let selectedRule='ben';
  const ruleOf = m => (selectedRule==='grace' && m.grace_prediction)
    ? {prediction:m.grace_prediction, odds:m.grace_odds, source:'Model', outcome:m.grace_outcome}
    : {prediction:m.prediction, odds:m.odds, source:m.odds_source, outcome:m.outcome};
  function ruleStats(){
    const tally={ben:{win:0,decided:0},grace:{win:0,decided:0}};
    for(const m of matches){
      if(!m.result_confirmed) continue;
      if(['Win','Lose'].includes(m.outcome)){tally.ben.decided++; if(m.outcome==='Win') tally.ben.win++;}
      if(['Win','Lose'].includes(m.grace_outcome)){tally.grace.decided++; if(m.grace_outcome==='Win') tally.grace.win++;}
    }
    const pct=t=>t.decided?`${Math.round(100*t.win/t.decided)}% <small>(${t.win}/${t.decided})</small>`:'—';
    const out=document.getElementById('rule-stats');
    if(out) out.innerHTML=`<span class="${selectedRule==='ben'?'on':''}">Ben Rule <b>${pct(tally.ben)}</b></span>`
      +`<span class="${selectedRule==='grace'?'on':''}">Grace Rule <b>${pct(tally.grace)}</b></span>`;
    return tally;
  }

  function render(){
    let q=search.trim().toLowerCase();
    const now=siteNow(), statusMatches=matches.filter(m=>inSelectedStatus(m,now));
    leagueButtons(statusMatches);
    updateDateTrigger();
    const filtered=statusMatches.filter(m=>(selectedDate==='All dates'||dayKey(m.kickoff)===selectedDate)&&(selectedLeague==='All leagues'||m.league===selectedLeague)&&(!q||`${m.home_team} ${m.away_team} ${m.league} ${(ruleOf(m).prediction)||''}`.toLowerCase().includes(q)));
    ruleStats();
    const shown=filtered.map(m=>{const r=ruleOf(m);return {...m,prediction:r.prediction,odds:r.odds,odds_source:r.source,outcome:r.outcome};});
    const html=leagues.map(l=>{const items=shown.filter(m=>m.league===l.name);if(!items.length)return '';return `<section class="league-card"><div class="league-head"><div class="league-icon">${image(l)}</div><div><div class="league-title">${esc(l.league_name)}</div><div class="league-sub">${esc(l.country||'Football')} · Football</div></div><span class="league-num">${items.length} ${items.length===1?'match':'matches'}</span></div><div class="column-head"><span>Date & time</span><span>Match</span><span>Prediction</span><span>Odds</span><span>Score</span><span>Result</span></div>${items.map(m=>{let d=dateParts(m.kickoff);return `<div class="match-row"><div class="date"><strong>${esc(d.day)}</strong><br>${esc(d.time)}</div><div class="teams"><div class="team-line"><span class="team-badge">${esc((m.home_team || '?')[0])}</span>${esc(m.home_team)}</div><div class="team-line"><span class="team-badge">${esc((m.away_team || '?')[0])}</span>${esc(m.away_team)}</div></div><div class="prediction">${esc(m.prediction)}<small>${esc(tipText[m.prediction]||'')}</small></div><div class="odds"><b>${m.odds ? esc(fmtOdds(m.odds)) : '—'}</b><small>${m.odds ? (m.odds_source === 'Bookmaker' ? 'book' : 'est') : ''}</small></div><div class="score">${m.result_confirmed?`${esc(m.home_score)} : ${esc(m.away_score)}`:'— : —'}<small>${m.result_confirmed?'FULL TIME':esc(m.provider_status||'PENDING')}</small></div><div class="result">${badge(m)}<button class="details" data-id="${esc(m.name)}" aria-label="View ${esc(m.home_team)} versus ${esc(m.away_team)} details">›</button></div></div>`}).join('')}</section>`}).join('');
    document.getElementById('match-list').innerHTML=html||`<div class="empty">${
      selectedDate==='All dates'
        ? (selectedStatus==='finished'?'No confirmed results to show.':'No matching pending predictions to show.')
        : `No ${selectedStatus==='finished'?'confirmed results':'pending predictions'} on ${esc(dateLabel(selectedDate))}${
            selectedStatus==='all'?' — try the Finished tab.':'.'}`
    }</div>`;
  }
  async function details(name) {
    let m=matches.find(x=>x.name===name); if(!m)return;
    const modal=document.getElementById('modal'); modal.classList.add('open');document.getElementById('close').focus();
    let d=dateParts(m.kickoff), league=leagues.find(l=>l.name===m.league);
    const header=`<div class="modal-league">${esc(league?.league_name||m.league)} · ${esc(d.day)} · ${esc(d.time)}</div><div class="modal-match"><span>${esc(m.home_team)}</span><span>${m.result_confirmed?`${esc(m.home_score)} : ${esc(m.away_score)}`:'vs'}</span><span>${esc(m.away_team)}</span></div><div class="modal-meta">${m.result_confirmed?'Full time (90 minutes)':'Pending final result'}</div><div class="modal-prediction"><span>Prediction: <b>${esc(m.prediction)} · ${esc(tipText[m.prediction]||'')}</b></span><span>Odds: <b>${m.odds ? esc(fmtOdds(m.odds)) : '—'}</b><small>${m.odds ? (m.odds_source === 'Bookmaker' ? 'bookmaker price' : 'Wakamaria estimate') : ''}</small></span>${badge(m)}</div><h3 class="history-title">Recent form</h3><p class="history-desc">Each team's last 3 available completed matches before this fixture</p>`;
    const body=document.getElementById('modal-body');body.innerHTML=header+'<p class="history-desc">Loading match history…</p>';
    try {let resp=await fetch('/api/method/wakamaria.api.match_details?name='+encodeURIComponent(name)); if(!resp.ok)throw Error();let {message:data}=await resp.json();
      const hist=(team,rows)=>`<div class="history-card"><h4>${esc(team)}</h4>${rows.length?rows.map(x=>`<div class="hist-row"><div>${esc(x.home)} vs ${esc(x.away)}<div class="hist-date">${esc(String(x.date).slice(0,10))}</div></div><strong>${esc(x.score[0])}–${esc(x.score[1])}</strong></div>`).join(''):'<div class="hist-row">No recent matches available yet.</div>'}</div>`;
      body.innerHTML=header+`<div class="history-grid">${hist(m.home_team,data.home)}${hist(m.away_team,data.away)}</div>`;
    } catch(e){body.innerHTML=header+'<p class="history-desc">Match history is currently unavailable.</p>';}
  }
  function setStatus(status) {
    selectedStatus=status;
    document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x.dataset.status===status));
    document.getElementById('predictions-link').classList.toggle('active',status!=='finished');
    document.getElementById('results-link').classList.toggle('active',status==='finished');
    render();
  }
  document.addEventListener('error',e=>{if(e.target.matches('[data-league-image]')&&e.target.src!==defaultImage)e.target.src=defaultImage},true);
  document.addEventListener('click',e=>{const dateTrigger=e.target.closest('#date-trigger');if(dateTrigger){toggleCalendar(document.getElementById('calendar').hidden);return}const calNav=e.target.closest('[data-cal-nav]');if(calNav){shiftMonth(Number(calNav.dataset.calNav));return}const calDay=e.target.closest('[data-cal-day]');if(calDay){selectedDate=calDay.dataset.calDay;toggleCalendar(false);render();return}const calClear=e.target.closest('[data-cal-clear]');if(calClear){selectedDate='All dates';toggleCalendar(false);render();return}if(!e.target.closest('.date-picker'))toggleCalendar(false);const league=e.target.closest('[data-league]');if(league){selectedLeague=league.dataset.league;render()}const tab=e.target.closest('[data-status]');if(tab)setStatus(tab.dataset.status);const detail=e.target.closest('[data-id]');if(detail)details(detail.dataset.id);if(e.target.id==='close'||e.target.id==='modal')document.getElementById('modal').classList.remove('open')});
  document.getElementById('search').addEventListener('input',e=>{search=e.target.value;render()});document.querySelectorAll('[data-rule]').forEach(b=>b.addEventListener('click',()=>{selectedRule=b.dataset.rule;document.querySelectorAll('[data-rule]').forEach(x=>x.classList.toggle('active',x===b));render();}));document.getElementById('predictions-link').addEventListener('click',()=>setStatus('all'));document.getElementById('results-link').addEventListener('click',()=>setStatus('finished'));document.addEventListener('keydown',e=>{if(e.key==='Escape'){document.getElementById('modal').classList.remove('open');toggleCalendar(false)}});
  let loaded=false, loading=false;
  async function refreshMatches() {
    if (loading) return;
    loading=true;
    try {
      const response=await fetch('/api/method/wakamaria.api.list_matches', {cache:'no-store'});
      if (!response.ok) throw Error();
      const data=await response.json();
      leagues=data.message.leagues||[];
      matches=(data.message.matches||[]).sort((a,b)=>String(a.kickoff).localeCompare(String(b.kickoff)));
      siteTimezone=data.message.timezone||'';
      const notes=document.querySelectorAll('.bottom-note span');
      if(notes[1]) notes[1].textContent='Times shown in '+siteTimezone;
      loaded=true; render();
    } catch (_) {
      if(!loaded) document.getElementById('match-list').innerHTML='<div class="empty">Unable to load matches. Please try again later.</div>';
    } finally { loading=false; }
  }
  refreshMatches();
  setInterval(refreshMatches, 60000);
})();
