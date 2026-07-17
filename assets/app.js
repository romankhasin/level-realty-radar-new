let database={items:[]};
let selectedStream='';

const normalize=v=>(v||'').toString().toLowerCase();
const escapeHtml=v=>(v||'').toString().replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));

function urgencyClass(item){
  return item.urgency==='Высокая'?'priority-high':'priority-mid';
}

function renderTopCard(item,index){
  return `<article class="top-card">
    <div class="top-number">${String(index+1).padStart(2,'0')}</div>
    <div class="top-content">
      <div class="meta"><span class="source">${escapeHtml(item.source)}</span><span>${escapeHtml(item.stream||'')}</span></div>
      <h3>${escapeHtml(item.title)}</h3>
      <p>${escapeHtml(item.level_value||'')}</p>
      <div class="foot">
        <span class="tag ${urgencyClass(item)}">${escapeHtml(item.urgency||'Средняя')}</span>
        <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">Открыть →</a>
      </div>
    </div>
  </article>`;
}

function renderCard(item){
  const date=new Date(item.date+'T12:00:00').toLocaleDateString('ru-RU');
  const comps=(item.competitors||[]).map(v=>`<span class="tag">${escapeHtml(v)}</span>`).join('');
  const teams=(item.team||[]).map(v=>`<span class="tag team">${escapeHtml(v)}</span>`).join('');
  const recs=(item.recommendations||[]).map(v=>`<li>${escapeHtml(v)}</li>`).join('');

  return `<article class="card">
    <div class="meta"><span class="source">${escapeHtml(item.source)}</span><span>${date}</span></div>
    <h2>${escapeHtml(item.title)}</h2>
    <div class="summary clamp">${escapeHtml(item.summary||'')}</div>
    <div class="tags">
      <span class="tag">${escapeHtml(item.stream||'Сигнал')}</span>
      <span class="tag">${escapeHtml(item.topic||'Новости')}</span>
      <span class="tag ${urgencyClass(item)}">${escapeHtml(item.urgency||'Средняя')}</span>
      ${comps}
    </div>
    <div class="analysis">
      <b>Почему это важно для Level</b>
      <p>${escapeHtml(item.level_value||'Материал требует дополнительной оценки.')}</p>
      ${recs?`<ul class="recommendations">${recs}</ul>`:''}
    </div>
    <div class="tags">${teams}</div>
    <div class="foot">
      <span>Релевантность ${Number(item.relevance_score||0)}</span>
      <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">Открыть →</a>
    </div>
  </article>`;
}

function fillSelect(id,values){
  const el=document.getElementById(id);
  if(!el)return;
  values.sort().forEach(v=>el.insertAdjacentHTML('beforeend',`<option>${escapeHtml(v)}</option>`));
}

function setStream(button,value){
  selectedStream=value;
  document.querySelectorAll('.stream-button').forEach(btn=>btn.classList.toggle('active',btn===button));
  if(window.streamFilter)streamFilter.value=value;
  render();
}

function render(){
  const text=normalize(searchInput.value);
  const source=sourceFilter.value;
  const topic=topicFilter.value;
  const competitor=competitorFilter.value;
  const dropdownStream=window.streamFilter?streamFilter.value:'';
  const stream=dropdownStream||selectedStream;

  const rows=database.items.filter(item=>{
    const haystack=normalize([
      item.title,item.summary,item.source,item.topic,item.stream,item.level_value,
      ...(item.competitors||[]),...(item.recommendations||[]),...(item.team||[])
    ].join(' '));
    return (!text||haystack.includes(text))
      &&(!source||item.source===source)
      &&(!topic||item.topic===topic)
      &&(!competitor||(item.competitors||[]).includes(competitor))
      &&(!stream||item.stream===stream);
  }).sort((a,b)=>(b.date||'').localeCompare(a.date||'')||(b.importance||0)-(a.importance||0));

  grid.innerHTML=rows.length?rows.map(renderCard).join(''):'<div class="empty">По выбранным фильтрам материалов нет.</div>';
}

function renderTop(){
  const today=database.items.map(i=>i.date).sort().reverse()[0];
  let candidates=database.items.filter(i=>i.date===today);
  if(candidates.length<5)candidates=database.items;
  candidates=candidates
    .sort((a,b)=>(b.importance||0)-(a.importance||0)||(b.relevance_score||0)-(a.relevance_score||0))
    .slice(0,5);
  topGrid.innerHTML=candidates.length?candidates.map(renderTopCard).join(''):'<div class="empty">После первого обновления здесь появятся главные материалы.</div>';
}

async function loadData(){
  try{
    const r=await fetch('./news.json?v='+Date.now(),{cache:'no-store'});
    if(!r.ok)throw new Error('HTTP '+r.status);
    const d=await r.json();
    database=Array.isArray(d)?{items:d}:d;
    database.items=database.items||[];

    const sources=[...new Set(database.items.map(i=>i.source).filter(Boolean))];
    const topics=[...new Set(database.items.map(i=>i.topic).filter(Boolean))];
    const streams=[...new Set(database.items.map(i=>i.stream).filter(Boolean))];
    const comps=[...new Set(database.items.flatMap(i=>i.competitors||[]))];

    fillSelect('sourceFilter',sources);
    fillSelect('topicFilter',topics);
    fillSelect('streamFilter',streams);
    fillSelect('competitorFilter',comps);

    total.textContent=database.items.length;
    week.textContent=database.items.filter(i=>new Date(i.date)>=Date.now()-7*864e5).length;
    sourcesCount.textContent=sources.length;
    competitorsCount.textContent=database.items.filter(i=>(i.competitors||[]).length).length;

    const updated=database.updated_at?new Date(database.updated_at).toLocaleString('ru-RU'):'ещё не запускался';
    const stats=database.stats?` · источников: ${database.stats.sources_ok} успешно, ${database.stats.sources_warning} без материалов, ${database.stats.sources_failed} ошибок`:'';
    status.textContent='Обновлено: '+updated+stats;

    renderTop();
    render();
  }catch(e){
    status.innerHTML=`<div class="error">Не удалось загрузить news.json: ${escapeHtml(e.message)}.</div>`;
    console.error(e);
  }
}
window.addEventListener('DOMContentLoaded',loadData);
