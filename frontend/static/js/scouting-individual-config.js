(function(){
  const root=document.querySelector('[data-reading-board]');
  if(!root)return;
  const key=`scouting-reading-categories:${root.dataset.playerId}`;
  const checks=[...root.querySelectorAll('[data-reading-toggle]')];
  const cards=[...root.querySelectorAll('[data-reading-category]')];
  const empty=root.querySelector('[data-reading-empty]');
  const defaults=(root.dataset.readingDefaults||'').split(',').filter(Boolean);
  let selected=defaults;
  try{
    const saved=JSON.parse(localStorage.getItem(key));
    if(Array.isArray(saved))selected=saved;
  }catch(_){ }
  const apply=()=>{
    const active=new Set(checks.filter(input=>input.checked).map(input=>input.value));
    cards.forEach(card=>{card.hidden=!active.has(card.dataset.readingCategory)});
    empty.hidden=active.size>0;
    try{localStorage.setItem(key,JSON.stringify([...active]))}catch(_){ }
  };
  checks.forEach(input=>{
    input.checked=selected.includes(input.value);
    input.addEventListener('change',apply);
  });
  apply();
})();
