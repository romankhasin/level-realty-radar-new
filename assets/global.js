let globalDatabase={items:[]};
let selectedCategory='';
let selectedRelevance='';

const byId=id=>document.getElementById(id);
const esc=v=>(v||'').toString().replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
const norm=v=>(v||'').toString().toLowerCase();

function stars(value){
  const n=Math.max(1,Math.min(5,Number(value||3)));
  return '★'.repeat(n)+'☆'.repeat(5-n);
}
function relClass(label){
  return label==='Высокая'?'relevance-high':label==='Средняя'?'relevance-medium':'relevance-low';
}
function renderGlobalCard(item){
  const date=new Date(item.date+'T12:00:00').toLocaleDateString('ru-RU');
  const ideas=(item.level_applications||[]).map(v=>`<li>${esc(v)}</li>`).join('');
  return `<article class="card global-card">
    <div class="meta"><span class="source">${esc(item.source)}</span><span>${date}</span></div>
    <h2>${esc(item.title)}</h2>
    <div class="summary clamp">${esc(item.summary||'')}</div>
    <div class="tags">
      <span class="tag global-category-tag">${esc(item.category||'Global')}</span>
      <span class="tag">${esc(item.region||'Global')}</span>
      <span class="tag ${relClass(item.relevance_label)}">${item.relevance_label==='Высокая'?'🔥 ':''}${esc(item.relevance_label||'Средняя')}</span>
    </div>
    <div class="analysis global-analysis">
      <b>Почему это важно для Level</b>
      <p>${esc(item.level_value||'Материал может содержать применимую зарубежную практику.')}</p>
      ${ideas?`<div class="application-title">Что можно адаптировать</div><ul class="recommendations">${ideas}</ul>`:''}
    </div>
    <div class="potential">
      <span>Потенциал внедрения</span>
      <b title="${Number(item.potential||3)} из 5">${stars(item.potential)}</b>
    </div>
    <div class="foot">
      <span>${esc(item.signal_type||'Мировая практика')}</span>
      <a href="${esc(item.url)}" target="_blank" rel="noopener">Открыть →</a>
    </div>
  </article>`;
}
function fill(id, values){
  const el=byId(id);
  [...new Set(values.filter(Boolean))].sort().forEach(v=>el.insertAdjacentHTML('beforeend',`<option>${esc(v)}</option>`));
}
function render(){
  const q=norm(byId('globalSearch')?.value);
  const region=byId('regionFilter')?.value||'';
  const source=byId('globalSourceFilter')?.value||'';
  const potential=Number(byId('potentialFilter')?.value||0);

  const rows=globalDatabase.items.filter(item=>{
    const hay=norm([item.title,item.summary,item.source,item.category,item.region,item.level_value,...(item.level_applications||[])].join(' '));
    return (!q||hay.includes(q))
      &&(!selectedCategory||item.category===selectedCategory)
      &&(!selectedRelevance||item.relevance_label===selectedRelevance)
      &&(!region||item.region===region)
      &&(!source||item.source===source)
      &&(!potential||Number(item.potential||0)>=potential);
  }).sort((a,b)=>(b.date||'').localeCompare(a.date||'')||Number(b.potential||0)-Number(a.potential||0));

  byId('globalGrid').innerHTML=rows.length?rows.map(renderGlobalCard).join(''):'<div class="empty">По выбранным фильтрам материалов нет.</div>';
}
async function loadGlobal(){
  try{
    const response=await fetch('./global_news.json?v='+Date.now(),{cache:'no-store'});
    if(!response.ok)throw new Error('HTTP '+response.status);
    const data=await response.json();
    globalDatabase=Array.isArray(data)?{items:data}:data;
    globalDatabase.items=globalDatabase.items||[];

    fill('regionFilter',globalDatabase.items.map(i=>i.region));
    fill('globalSourceFilter',globalDatabase.items.map(i=>i.source));

    byId('globalTotal').textContent=globalDatabase.items.length;
    byId('globalWeek').textContent=globalDatabase.items.filter(i=>new Date(i.date+'T12:00:00')>=Date.now()-7*864e5).length;
    byId('globalSources').textContent=new Set(globalDatabase.items.map(i=>i.source)).size;
    byId('highPotential').textContent=globalDatabase.items.filter(i=>Number(i.potential||0)>=4).length;

    const updated=globalDatabase.updated_at?new Date(globalDatabase.updated_at).toLocaleString('ru-RU'):'ещё не запускался';
    const s=globalDatabase.stats;
    byId('globalStatus').textContent='Обновлено: '+updated+(s?` · источников: ${s.sources_ok} успешно, ${s.sources_warning} без материалов, ${s.sources_failed} ошибок`:'');
    render();
  }catch(e){
    byId('globalStatus').innerHTML=`<div class="error">Не удалось загрузить global_news.json: ${esc(e.message)}.</div>`;
  }
}
window.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('.global-category').forEach(btn=>btn.addEventListener('click',()=>{
    selectedCategory=btn.dataset.category||'';
    document.querySelectorAll('.global-category').forEach(x=>x.classList.toggle('active',x===btn));
    render();
  }));
  document.querySelectorAll('.global-relevance').forEach(btn=>btn.addEventListener('click',()=>{
    selectedRelevance=btn.dataset.relevance||'';
    document.querySelectorAll('.global-relevance').forEach(x=>x.classList.toggle('active',x===btn));
    render();
  }));
  ['globalSearch','regionFilter','globalSourceFilter','potentialFilter'].forEach(id=>{
    const el=byId(id);
    el.addEventListener(id==='globalSearch'?'input':'change',render);
  });
  loadGlobal();
});