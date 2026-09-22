(function(){
  window.initReportBuilder=function(root){
    const form=root.querySelector('[data-report-form]');if(!form||form.dataset.ready)return;form.dataset.ready='true';
    const defaults=JSON.parse(form.dataset.reportDefaults||'{}'),list=form.querySelector('[data-report-sections]'),order=form.querySelector('[data-report-order]');
    const sync=()=>{order.value=[...list.querySelectorAll('[data-section]')].map(el=>el.dataset.section).join(',')};let dragged=null;
    list.querySelectorAll('[draggable]').forEach(card=>{card.addEventListener('dragstart',()=>{dragged=card;card.classList.add('is-dragging')});card.addEventListener('dragend',()=>{card.classList.remove('is-dragging');dragged=null;sync()});card.addEventListener('dragover',event=>{event.preventDefault();if(!dragged||dragged===card)return;const box=card.getBoundingClientRect();list.insertBefore(dragged,event.clientY<box.top+box.height/2?card:card.nextSibling)})});
    const sectionChecks=()=>[...form.querySelectorAll('input[name="secoes"]')];
    const syncOrientation=()=>{const format=form.querySelector('input[name="formato"]:checked')?.value,portrait=form.querySelector('input[name="orientacao"][value="retrato"]'),landscape=form.querySelector('input[name="orientacao"][value="paisagem"]');if(!portrait||!landscape)return;portrait.disabled=format==='a3';if(format==='a3')landscape.checked=true};
    form.querySelectorAll('input[name="formato"]').forEach(input=>input.addEventListener('change',syncOrientation));
    form.querySelectorAll('[data-sections]').forEach(button=>button.addEventListener('click',()=>{const mode=button.dataset.sections,format=form.querySelector('input[name="formato"]:checked').value;sectionChecks().forEach(input=>input.checked=mode==='all'||(mode==='defaults'&&(defaults[format]||[]).includes(input.value)))}));
    form.querySelectorAll('[data-system-preset]').forEach(button=>button.addEventListener('click',()=>{const format=button.dataset.systemPreset;form.querySelector(`input[name="formato"][value="${format}"]`).checked=true;sectionChecks().forEach(input=>input.checked=(defaults[format]||[]).includes(input.value));if(format==='a3')form.querySelector('input[name="orientacao"][value="paisagem"]').checked=true}));
    form.querySelectorAll('[data-entities]').forEach(button=>button.addEventListener('click',()=>form.querySelectorAll('input[name="entidades"]').forEach(input=>input.checked=button.dataset.entities==='all')));
    form.addEventListener('submit',sync);sync();syncOrientation();
  };
})();
