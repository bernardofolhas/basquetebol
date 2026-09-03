(() => {
  const root = document.querySelector("[data-statboard]");
  if (!root) return;
  const gameId = Number(root.dataset.gameId);
  const userId = Number(root.dataset.userId);
  const canEdit = root.dataset.canEdit === "true";
  const serverEvents = JSON.parse(root.querySelector("[data-stats-events]")?.textContent || "[]");
  const storageKey = `basket-stats:${userId}:${gameId}`;
  const clockKey = `${storageKey}:clock`;
  const labels = {ll_c:"LL convertido",ll_f:"LL falhado",dois_c:"2P convertido",dois_f:"2P falhado",tres_c:"3P convertido",tres_f:"3P falhado",ressalto_ofensivo:"Ressalto ofensivo",ressalto_defensivo:"Ressalto defensivo",assistencia:"Assistência",roubo:"Roubo",perda:"Perda",desarme:"Desarme",falta:"Falta pessoal",falta_sofrida:"Falta sofrida"};
  const points = {ll_c:1,dois_c:2,tres_c:3};
  let dirty = loadJson(storageKey, []);
  let events = mergeEvents(serverEvents, dirty);
  let selectedPlayer = null;
  let clock = loadJson(clockKey, {seconds:600,running:false,period:1,updatedAt:Date.now()});
  let timer = null;
  let syncTimer = null;
  let syncing = false;
  let syncRequested = false;

  function loadJson(key, fallback) { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch (_) { return fallback; } }
  function saveLocal() { localStorage.setItem(storageKey, JSON.stringify(dirty)); localStorage.setItem(clockKey, JSON.stringify({...clock,updatedAt:Date.now()})); }
  function mergeEvents(base, pending) { const map=new Map(base.map(item=>[item.client_uid,item])); pending.forEach(item=>map.set(item.client_uid,{...map.get(item.client_uid),...item})); return [...map.values()]; }
  function uid() { return crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`; }
  function active() { return events.filter(item=>!item.anulado); }
  function currentSeconds() { return Math.max(0, Number(clock.seconds)||0); }
  function formatClock(seconds) { return `${String(Math.floor(seconds/60)).padStart(2,"0")}:${String(seconds%60).padStart(2,"0")}`; }
  function clockElement() { return root.querySelector("[data-clock]"); }
  function updateClock() { if(clockElement())clockElement().textContent=formatClock(currentSeconds()); const period=root.querySelector("[data-period]"); if(period)period.value=String(clock.period); }
  function startTimer() { clearInterval(timer); if(!clock.running)return; timer=setInterval(()=>{ if(clock.seconds<=0){clock.running=false;clearInterval(timer);}else clock.seconds-=1;updateClock();saveLocal(); },1000); }
  function markDirty(event) { dirty=dirty.filter(item=>item.client_uid!==event.client_uid); dirty.push({...event,sincronizado:false}); saveLocal(); }
  function addEvent(type, side="equipa") {
    if(!canEdit)return;
    if(side==="equipa"&&!selectedPlayer){notify("Seleciona primeiro um atleta.","danger");return;}
    const playerButton=selectedPlayer?root.querySelector(`[data-player-id="${selectedPlayer}"]`):null;
    const event={client_uid:uid(),jogador_id:side==="equipa"?selectedPlayer:null,jogador:playerButton?.dataset.playerName||null,lado:side,tipo:type,periodo:Number(root.querySelector("[data-period]")?.value||1),segundos_restantes:currentSeconds(),anulado:false,sincronizado:false};
    events.push(event); markDirty(event); render(); scheduleSync();
  }
  function undo() { const event=[...events].reverse().find(item=>!item.anulado); if(!event){notify("Não existem ações para desfazer.");return;} event.anulado=true;markDirty(event);render();scheduleSync(); }
  function notify(message,tone="warning") { const stack=root.querySelector("[data-warning-stack]"); if(!stack)return; const item=document.createElement("div");item.className=`stat-warning${tone==="danger"?" is-danger":""}`;item.textContent=message;stack.prepend(item);stack.hidden=false;setTimeout(()=>{item.remove();stack.hidden=!stack.children.length},4500); }
  async function sync(showFeedback=true) {
    if(syncing){syncRequested=true;return;}
    if(!canEdit||!dirty.length){if(showFeedback)notify("Todos os dados já estão sincronizados.");updateConnection();return;}
    if(!navigator.onLine){if(showFeedback)notify("Sem internet. Os dados ficaram guardados neste dispositivo.");updateConnection();return;}
    syncing=true;
    syncRequested=false;
    let completed=false;
    const batch=[...dirty];
    const button=root.querySelector("[data-stat-sync]");if(button)button.disabled=true;
    try{
      const response=await fetch(`/estatisticas/jogos/${gameId}/sincronizar`,{method:"POST",headers:{"Content-Type":"application/json","X-CSRF-Token":document.querySelector('meta[name="csrf-token"]')?.content||""},body:JSON.stringify({eventos:batch})});
      const result=await response.json();if(!response.ok||!result.ok)throw new Error(result.message||"Falha de sincronização");
      const sent=new Set(batch.map(item=>item.client_uid));dirty=dirty.filter(item=>!sent.has(item.client_uid));events=mergeEvents(result.eventos,dirty);if(dirty.length)localStorage.setItem(storageKey,JSON.stringify(dirty));else localStorage.removeItem(storageKey);completed=true;render();if(showFeedback)notify("Estatísticas sincronizadas com sucesso.");
    }catch(error){if(showFeedback)notify("Não foi possível sincronizar. Nada foi perdido.","danger");}
    finally{syncing=false;if(button)button.disabled=false;updateConnection();if(navigator.onLine&&dirty.length&&(syncRequested||completed)){syncRequested=false;setTimeout(()=>sync(false),150);}}
  }
  function scheduleSync(){if(!navigator.onLine)return;clearTimeout(syncTimer);syncTimer=setTimeout(()=>sync(false),650);}
  function totalsFor(playerId) {
    const list=active().filter(item=>item.lado==="equipa"&&item.jogador_id===playerId);const count=type=>list.filter(item=>item.tipo===type).length;
    const llc=count("ll_c"),llt=llc+count("ll_f"),c2=count("dois_c"),t2=c2+count("dois_f"),c3=count("tres_c"),t3=c3+count("tres_f"),ro=count("ressalto_ofensivo"),rd=count("ressalto_defensivo"),ast=count("assistencia"),stl=count("roubo"),to=count("perda"),blk=count("desarme"),pf=count("falta"),pts=llc+c2*2+c3*3;return{pts,llc,llt,c2,t2,c3,t3,ro,rd,rt:ro+rd,ast,stl,to,blk,pf,eff:pts+ro+rd+ast+stl+blk-(llt-llc)-(t2-c2)-(t3-c3)-to};
  }
  function renderBoxscore(){root.querySelectorAll("[data-boxscore-player]").forEach(row=>{const id=Number(row.dataset.boxscorePlayer),s=totalsFor(id),cells=row.querySelectorAll("td");const values=[s.pts,`${s.llc}/${s.llt}`,`${s.c2}/${s.t2}`,`${s.c3}/${s.t3}`,s.ro,s.rd,s.rt,s.ast,s.stl,s.to,s.blk,s.pf,s.eff];values.forEach((value,index)=>cells[index+1].textContent=value);const badge=root.querySelector(`[data-player-points="${id}"]`);if(badge)badge.textContent=`${s.pts} pts`;});}
  function renderScores(){["equipa","adversario"].forEach(side=>{const score=active().filter(item=>item.lado===side).reduce((sum,item)=>sum+(points[item.tipo]||0),0);root.querySelector(`[data-score="${side}"]`).textContent=score;});}
  function renderFeed(){const target=root.querySelector("[data-stat-feed]");if(!target)return;const list=[...active()].reverse().slice(0,20);target.innerHTML="";if(!list.length){target.innerHTML='<p class="stat-feed-empty">As ações surgem aqui durante o jogo.</p>';return;}list.forEach(item=>{const node=document.createElement("div");node.className="stat-feed-item";const who=item.lado==="adversario"?"Adversário":(item.jogador||"Atleta");node.innerHTML=`<div><strong></strong><span></span></div><b></b>`;node.querySelector("strong").textContent=who;node.querySelector("span").textContent=labels[item.tipo]||item.tipo;node.querySelector("b").textContent=`${item.periodo}º · ${formatClock(item.segundos_restantes??0)}`;target.appendChild(node);});}
  function renderWarnings(){const stack=root.querySelector("[data-warning-stack]");if(!stack)return;stack.querySelectorAll("[data-auto-warning]").forEach(item=>item.remove());const list=[];root.querySelectorAll("[data-boxscore-player]").forEach(row=>{const s=totalsFor(Number(row.dataset.boxscorePlayer));if(s.pf>=5)list.push([`${row.cells[0].textContent.trim()}: ${s.pf} faltas, atleta excluído.`,"danger"]);else if(s.pf===4)list.push([`${row.cells[0].textContent.trim()}: 4 faltas pessoais.`,"warning"]);});const teamFouls=active().filter(item=>item.lado==="equipa"&&item.tipo==="falta"&&item.periodo===Number(clock.period)).length;if(teamFouls>=5)list.push([`${teamFouls} faltas de equipa no ${clock.period}º período.`,"warning"]);list.reverse().forEach(([message,tone])=>{const item=document.createElement("div");item.dataset.autoWarning="true";item.className=`stat-warning${tone==="danger"?" is-danger":""}`;item.textContent=message;stack.prepend(item);});stack.hidden=!stack.children.length;}
  function updateConnection(){const online=navigator.onLine;root.querySelector("[data-online-dot]")?.classList.toggle("is-online",online);root.querySelector("[data-online-label]").textContent=online?"Online":"Modo offline";root.querySelector("[data-sync-label]").textContent=dirty.length?`${dirty.length} ação(ões) por sincronizar`:"Tudo sincronizado";}
  function render(){renderScores();renderBoxscore();renderFeed();renderWarnings();updateConnection();updateClock();root.querySelectorAll("[data-stat-action]").forEach(button=>button.disabled=!selectedPlayer);}

  root.querySelectorAll("[data-player-id]").forEach(button=>button.addEventListener("click",()=>{selectedPlayer=Number(button.dataset.playerId);root.querySelectorAll("[data-player-id]").forEach(item=>item.classList.toggle("is-selected",item===button));root.querySelector("[data-selected-player]").textContent=button.dataset.playerName;render();}));
  root.querySelectorAll("[data-stat-action]").forEach(button=>button.addEventListener("click",()=>addEvent(button.dataset.statAction)));
  root.querySelectorAll("[data-opponent-action]").forEach(button=>button.addEventListener("click",()=>addEvent(button.dataset.opponentAction,"adversario")));
  root.querySelector("[data-stat-undo]")?.addEventListener("click",undo);root.querySelector("[data-stat-sync]")?.addEventListener("click",()=>sync(true));
  root.querySelector("[data-period]")?.addEventListener("change",event=>{clock.period=Number(event.target.value);clock.seconds=600;clock.running=false;startTimer();saveLocal();render();});
  clockElement()?.addEventListener("click",()=>{clock.running=!clock.running;startTimer();saveLocal();});
  document.addEventListener("keydown",event=>{if(!canEdit||event.ctrlKey||event.metaKey||/INPUT|TEXTAREA|SELECT/.test(event.target.tagName))return;const map={"1":"ll_c","2":"dois_c","3":"tres_c",q:"ll_f",w:"dois_f",e:"tres_f",r:"ressalto_defensivo",o:"ressalto_ofensivo",a:"assistencia",s:"roubo",t:"perda",b:"desarme",f:"falta"};if(event.key.toLowerCase()==="z"){event.preventDefault();undo();}else if(map[event.key.toLowerCase()]){event.preventDefault();addEvent(map[event.key.toLowerCase()]);}});
  window.addEventListener("online",()=>{updateConnection();sync(false)});window.addEventListener("offline",()=>{updateConnection();notify("Ligação perdida. Podes continuar: as ações ficam guardadas neste dispositivo.");});window.addEventListener("beforeunload",saveLocal);
  if("serviceWorker" in navigator){navigator.serviceWorker.ready.then(registration=>registration.active?.postMessage({type:"CACHE_STATS_PAGE",url:window.location.href})).catch(()=>{});}
  updateClock();startTimer();render();if(navigator.onLine)sync(false);
})();
