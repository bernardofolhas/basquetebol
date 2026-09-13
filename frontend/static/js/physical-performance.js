(() => {
  const num = value => { const n = Number(String(value ?? '').replace(',', '.')); return Number.isFinite(n) ? n : null; };
  const safe = value => String(value ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

  document.querySelectorAll('[data-physical-test-card]').forEach(card => card.addEventListener('click', () => {
    document.querySelectorAll('[data-physical-test-card]').forEach(item => item.setAttribute('aria-selected', String(item === card)));
    document.querySelectorAll('[data-physical-test-panel]').forEach(panel => { panel.hidden = panel.dataset.physicalTestPanel !== card.dataset.physicalTestCard; });
  }));
  document.querySelectorAll('[data-result-filters]').forEach(filters => {
    const panel = filters.closest('[data-physical-test-panel]'), body = panel.querySelector('[data-result-rows]'), rows = [...body.children];
    const from = filters.querySelector('[data-filter-from]'), to = filters.querySelector('[data-filter-to]'), player = filters.querySelector('[data-filter-player]'), sort = filters.querySelector('[data-filter-sort]');
    const apply = () => {
      const visible = rows.filter(row => (!from.value || row.dataset.date >= from.value) && (!to.value || row.dataset.date <= to.value) && (!player.value || row.dataset.player === player.value));
      const [field, direction] = sort.value.split('-'), key = field === 'asym' ? 'asymmetry' : field;
      visible.sort((a,b) => { const av = field === 'date' ? a.dataset.date : num(a.dataset[key]), bv = field === 'date' ? b.dataset.date : num(b.dataset[key]); if (av === null) return 1; if (bv === null) return -1; return (av > bv ? 1 : av < bv ? -1 : 0) * (direction === 'asc' ? 1 : -1); });
      rows.forEach(row => { row.hidden = !visible.includes(row); }); visible.forEach(row => body.append(row)); panel.querySelector('[data-filter-empty]').hidden = Boolean(visible.length);
    };
    filters.querySelectorAll('input,select').forEach(input => input.addEventListener('input', apply));
    filters.querySelector('[data-clear-result-filters]').addEventListener('click', () => { from.value=''; to.value=''; player.value=''; sort.value='date-desc'; apply(); });
  });

  const dialog = document.getElementById('physical-test-dialog');
  if (dialog) {
    const definition = dialog.querySelector('[data-test-definition]'), newTest = dialog.querySelector('[data-new-test-definition]'), laterality = dialog.querySelector('[data-test-laterality]'), name = dialog.querySelector('[name="tipo_teste"]');
    const mode = value => dialog.querySelectorAll('[data-unilateral-definition],[data-unilateral-result]').forEach(element => { element.hidden = value !== 'unilateral'; });
    const sync = () => { const existing = Boolean(definition.value), option = definition.selectedOptions[0]; newTest.hidden = existing; name.required = !existing; if (existing) laterality.value = option.dataset.laterality || 'bilateral'; mode(laterality.value); };
    definition.addEventListener('change', sync); laterality.addEventListener('change', () => mode(laterality.value));
    dialog.querySelectorAll('.physical-athlete-row').forEach(row => {
      const left = row.querySelector('[name^="resultado_esquerdo_"]'), right = row.querySelector('[name^="resultado_direito_"]'), asym = row.querySelector('[data-asymmetry-input]');
      const calculate = () => { const l=num(left.value), r=num(right.value); if(l===null || r===null || asym.dataset.manual==='true') return; const base=Math.max(Math.abs(l),Math.abs(r)); asym.value=base?(Math.abs(l-r)/base*100).toFixed(2):'0.00'; };
      left.addEventListener('input',calculate); right.addEventListener('input',calculate); asym.addEventListener('change',()=>{asym.dataset.manual=asym.value?'true':'false';});
    });
    document.querySelectorAll('[data-open-physical-test]').forEach(button => button.addEventListener('click',()=>{sync();dialog.showModal();}));
    dialog.querySelectorAll('[data-close-physical-test]').forEach(button => button.addEventListener('click',()=>dialog.close()));
    dialog.querySelector('[data-select-athletes]').addEventListener('click',()=>dialog.querySelectorAll('[name="jogador_ids"]').forEach(input=>{input.checked=true;}));
    dialog.querySelector('[data-clear-athletes]').addEventListener('click',()=>dialog.querySelectorAll('[name="jogador_ids"]').forEach(input=>{input.checked=false;}));
  }

  const root = document.querySelector('.physical-analysis'); if (!root) return;
  let data=[]; try { data=JSON.parse(root.querySelector('[data-physical-analysis-source]').textContent); } catch (_) {}
  const scope=root.querySelector('[data-analysis-scope]'), test=root.querySelector('[data-analysis-test]'), from=root.querySelector('[data-analysis-from]'), to=root.querySelector('[data-analysis-to]'), checks=[...root.querySelectorAll('[data-analysis-player]')];
  const mean = values => values.length ? values.reduce((a,b)=>a+b,0)/values.length : null;
  const filtered = () => { let ids=checks.filter(i=>i.checked).map(i=>+i.value); if(scope.value==='individual') ids=ids.slice(0,1); return data.filter(x=>(!test.value||x.definicao_id===+test.value)&&(!from.value||x.data>=from.value)&&(!to.value||x.data<=to.value)&&(['team','test'].includes(scope.value)||ids.includes(x.jogador_id))); };
  const ranking = (items,key,suffix='') => { const groups={}; items.forEach(x=>{const v=num(x[key]);if(v!==null)(groups[x.jogador]??=[]).push(v);}); const rows=Object.entries(groups).map(([name,values])=>({name,value:mean(values)})).sort((a,b)=>b.value-a.value), max=Math.max(...rows.map(x=>x.value),1); return rows.length?rows.map(x=>`<div class="physical-rank-row"><span>${safe(x.name)}</span><div class="physical-rank-track"><i style="width:${Math.max(3,x.value/max*100)}%"></i></div><strong>${x.value.toFixed(1)}${suffix}</strong></div>`).join(''):'<p class="physical-empty">Sem dados para esta seleção.</p>'; };
  const render = () => {
    const items=filtered(), results=items.map(x=>num(x.resultado)).filter(x=>x!==null), asym=items.map(x=>num(x.assimetria)).filter(x=>x!==null);
    root.querySelector('[data-physical-kpi="measurements"]').textContent=items.length; root.querySelector('[data-physical-kpi="players"]').textContent=new Set(items.map(x=>x.jogador_id)).size; root.querySelector('[data-physical-kpi="average"]').textContent=test.value&&results.length?mean(results).toFixed(2):'—'; root.querySelector('[data-physical-kpi="asymmetry"]').textContent=asym.length?`${mean(asym).toFixed(1)}%`:'—';
    const points=items.filter(x=>num(x.resultado)!==null).sort((a,b)=>a.data.localeCompare(b.data)), values=points.map(x=>num(x.resultado)), low=Math.min(...values,0), high=Math.max(...values,1), span=high-low||1;
    root.querySelector('[data-physical-trend]').innerHTML=points.length?points.map(x=>`<i class="physical-trend-bar" style="height:${20+(num(x.resultado)-low)/span*80}%" data-label="${safe(x.data)} · ${safe(x.jogador)} · ${num(x.resultado)}"></i>`).join(''):'<p class="physical-empty">Sem resultados numéricos.</p>';
    root.querySelector('[data-physical-ranking]').innerHTML=ranking(items,'resultado'); root.querySelector('[data-physical-asymmetry]').innerHTML=ranking(items,'assimetria','%');
    root.querySelector('[data-physical-analysis-table]').innerHTML=items.length?`<table><thead><tr><th>Data</th><th>Atleta</th><th>Teste</th><th>Resultado</th><th>Assimetria</th></tr></thead><tbody>${items.slice(0,100).map(x=>`<tr><td>${safe(x.data)}</td><td>${safe(x.jogador)}</td><td>${safe(x.teste)}</td><td>${x.resultado??'—'} ${safe(x.unidade||'')}</td><td>${x.assimetria??'—'}${x.assimetria!=null?'%':''}</td></tr>`).join('')}</tbody></table>`:'<p class="physical-empty">Sem dados para esta seleção.</p>';
  };
  root.querySelectorAll('select,input').forEach(input=>input.addEventListener('input',render)); render();
})();
