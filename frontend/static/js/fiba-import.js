document.addEventListener("DOMContentLoaded",()=>{
  const root=document.querySelector("[data-fiba-import]");
  if(!root)return;
  const gameId=root.dataset.gameId;
  const csrf=document.querySelector('meta[name="csrf-token"]')?.content||"";
  const feedback=root.querySelector("[data-fiba-feedback]");
  const preview=root.querySelector("[data-fiba-preview]");
  const teamSelect=root.querySelector("[data-fiba-team]");
  const mappingsRoot=root.querySelector("[data-fiba-mappings]");
  const optionsTemplate=root.querySelector("[data-local-player-options]");
  let currentSource="file";
  let currentForm=null;
  let previewData=null;

  const showFeedback=(message,tone="info")=>{
    feedback.hidden=false;
    feedback.className=`fiba-feedback is-${tone}`;
    feedback.textContent=message;
  };
  const clock=value=>value===null||value===undefined?"–":`${String(Math.floor(value/60)).padStart(2,"0")}:${String(value%60).padStart(2,"0")}`;
  const updateMappedCount=()=>{
    const selects=[...mappingsRoot.querySelectorAll("select")];
    root.querySelector("[data-fiba-mapped-count]").textContent=`${selects.filter(item=>item.value).length}/${selects.length} associados`;
  };
  const appendOption=(select,value,label)=>{
    const option=document.createElement("option");
    option.value=String(value??"");
    option.textContent=label;
    select.append(option);
  };
  const renderMappings=()=>{
    const team=teamSelect.value;
    const players=(previewData?.jogadores||[]).filter(item=>item.equipa_numero===team);
    mappingsRoot.innerHTML="";
    if(!players.length){mappingsRoot.innerHTML='<p class="fiba-empty">O ficheiro não apresenta o plantel desta equipa. As ações serão importadas e poderão ficar sem atleta associado.</p>';updateMappedCount();return;}
    players.forEach(player=>{
      const row=document.createElement("label");
      row.className="fiba-mapping-row";
      const external=document.createElement("span");
      const name=document.createElement("strong");
      name.textContent=`${player.numero?`#${player.numero} · `:""}${player.nome}`;
      const reason=document.createElement("small");
      reason.textContent=player.motivo||`ID externo: ${player.identificador}`;
      external.append(name,reason);
      const select=document.createElement("select");
      select.dataset.externalId=player.identificador;
      select.innerHTML=optionsTemplate.innerHTML;
      if(player.jogador_id_sugerido)select.value=String(player.jogador_id_sugerido);
      select.addEventListener("change",updateMappedCount);
      row.append(external,select);
      mappingsRoot.append(row);
    });
    updateMappedCount();
  };
  const renderPreview=data=>{
    previewData=data;
    root.querySelector("[data-fiba-supported]").textContent=data.eventos_suportados;
    root.querySelector("[data-fiba-ignored]").textContent=data.eventos_ignorados;
    root.querySelector("[data-fiba-format]").textContent=data.formato.toUpperCase();
    teamSelect.innerHTML="";
    (data.equipas||[]).forEach(item=>appendOption(teamSelect,item.numero,item.nome));
    const teamByName=(data.equipas||[]).find(item=>item.nome.toLowerCase().includes("benfica"));
    if(teamByName)teamSelect.value=teamByName.numero;
    renderMappings();
    const sample=root.querySelector("[data-fiba-sample]");
    sample.innerHTML="";
    (data.amostra||[]).forEach(item=>{
      const row=document.createElement("tr");
      [item.periodo,clock(item.segundos_restantes),item.tipo.replaceAll("_"," "),item.jogador_nome||item.jogador_externo||"–",item.posicao_x===null?"–":`${item.posicao_x.toFixed(1)} / ${item.posicao_y.toFixed(1)}`].forEach(value=>{
        const cell=document.createElement("td");cell.textContent=String(value);row.append(cell);
      });
      sample.append(row);
    });
    preview.hidden=false;
    preview.scrollIntoView({behavior:"smooth",block:"start"});
  };
  teamSelect.addEventListener("change",renderMappings);

  root.querySelectorAll("[data-fiba-source]").forEach(form=>form.addEventListener("submit",async event=>{
    event.preventDefault();
    currentForm=form;
    currentSource=form.dataset.fibaSource;
    const button=form.querySelector('button[type="submit"]');
    const original=button.textContent;
    button.disabled=true;button.textContent="A analisar…";
    feedback.hidden=true;preview.hidden=true;
    try{
      const response=await fetch(`/estatisticas/jogos/${gameId}/fiba/previsualizar-${currentSource}`,{method:"POST",headers:{"X-CSRF-Token":csrf,"X-Requested-With":"XMLHttpRequest"},body:new FormData(form)});
      const data=await response.json();
      if(!response.ok||!data.ok)throw new Error(data.message||"Não foi possível analisar os dados.");
      renderPreview(data);
      showFeedback(`${data.eventos_suportados} ações reconhecidas. Confirma agora as associações.`,"success");
    }catch(error){showFeedback(error.message,"error");}
    finally{button.disabled=false;button.textContent=original;}
  }));

  root.querySelector("[data-fiba-confirm]").addEventListener("click",async event=>{
    if(!currentForm||!previewData)return;
    const button=event.currentTarget;
    const mapping={};
    mappingsRoot.querySelectorAll("select[data-external-id]").forEach(select=>{if(select.value)mapping[select.dataset.externalId]=Number(select.value);});
    const body=new FormData(currentForm);
    body.append("equipa_ficheiro",teamSelect.value);
    body.append("mapeamentos",JSON.stringify(mapping));
    button.disabled=true;button.textContent="A importar…";
    try{
      const response=await fetch(`/estatisticas/jogos/${gameId}/fiba/importar-${currentSource}`,{method:"POST",headers:{"X-CSRF-Token":csrf,"X-Requested-With":"XMLHttpRequest"},body});
      const data=await response.json();
      if(!response.ok||!data.ok)throw new Error(data.message||"Não foi possível concluir a importação.");
      const unmapped=data.sem_mapeamento?` ${data.sem_mapeamento} ações ficaram sem atleta associado.`:"";
      showFeedback(`Importação concluída: ${data.criadas} ações adicionadas e ${data.atualizadas} atualizadas.${unmapped}`,"success");
      button.textContent="Importação concluída";
      root.querySelectorAll("[data-fiba-result-link]").forEach(item=>item.remove());
      const link=document.createElement("a");link.className="ds-button ds-button-secondary";link.dataset.fibaResultLink="";link.href=data.destino;link.textContent="Abrir folha estatística";button.after(link);
    }catch(error){showFeedback(error.message,"error");button.disabled=false;button.textContent="Importar para esta folha";}
  });
});
