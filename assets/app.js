let database={items:[]};

const normalize=value=>(value||'').toString().toLowerCase();
const escapeHtml=value=>(value||'').toString().replace(/[&<>"']/g,char=>({
  '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'
}[char]));

function renderCard(item){
  const date=new Date(item.date+'T12:00:00').toLocaleDateString('ru-RU');
  const competitorTags=(item.competitors||[])
    .map(value=>`<span class="tag">${escapeHtml(value)}</span>`)
    .join('');

  const priorityClass=item.priority==='Высокий'?'priority-high':'priority-mid';
  const recommendations=(item.recommendations||[])
    .map(value=>`<li>${escapeHtml(value)}</li>`)
    .join('');

  return `<article class="card">
    <div class="meta">
      <span class="source">${escapeHtml(item.source)}</span>
      <span>${date}</span>
    </div>

    <h2>${escapeHtml(item.title)}</h2>
    <div class="summary">${escapeHtml(item.summary||'')}</div>

    <div class="tags">
      <span class="tag">${escapeHtml(item.topic||'Новости')}</span>
      <span class="tag">${escapeHtml(item.signal_type||'Сигнал')}</span>
      <span class="tag ${priorityClass}">${escapeHtml(item.priority||'Средний')}</span>
      ${competitorTags}
    </div>

    <div class="analysis">
      <b>Почему это важно для Level</b>
      <p>${escapeHtml(item.level_value||'Материал требует дополнительной оценки применимости для Level Group.')}</p>
      ${recommendations?`<ul class="recommendations">${recommendations}</ul>`:''}
    </div>

    <div class="foot">
      <span>Важность ${Number(item.importance||0)}%</span>
      <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">Открыть →</a>
    </div>
  </article>`;
}

function fillSelect(id,values){
  const element=document.getElementById(id);
  values.sort().forEach(value=>{
    element.insertAdjacentHTML('beforeend',`<option>${escapeHtml(value)}</option>`);
  });
}

function render(){
  const text=normalize(document.getElementById('searchInput').value);
  const source=document.getElementById('sourceFilter').value;
  const topic=document.getElementById('topicFilter').value;
  const competitor=document.getElementById('competitorFilter').value;

  const rows=database.items
    .filter(item=>{
      const haystack=normalize([
        item.title,item.summary,item.source,item.topic,item.signal_type,
        item.level_value,...(item.competitors||[]),...(item.recommendations||[])
      ].join(' '));

      return (!text||haystack.includes(text))
        &&(!source||item.source===source)
        &&(!topic||item.topic===topic)
        &&(!competitor||(item.competitors||[]).includes(competitor));
    })
    .sort((a,b)=>(b.date||'').localeCompare(a.date||'')||(b.importance||0)-(a.importance||0));

  document.getElementById('grid').innerHTML=rows.length
    ?rows.map(renderCard).join('')
    :'<div class="empty">По выбранным фильтрам новостей нет.</div>';
}

async function loadData(){
  const status=document.getElementById('status');

  try{
    const response=await fetch('./news.json?v='+Date.now(),{cache:'no-store'});
    if(!response.ok)throw new Error('HTTP '+response.status);

    const data=await response.json();
    database=Array.isArray(data)?{items:data}:data;
    database.items=database.items||[];

    const sources=[...new Set(database.items.map(item=>item.source).filter(Boolean))];
    const topics=[...new Set(database.items.map(item=>item.topic).filter(Boolean))];
    const competitors=[...new Set(database.items.flatMap(item=>item.competitors||[]))];

    fillSelect('sourceFilter',sources);
    fillSelect('topicFilter',topics);
    fillSelect('competitorFilter',competitors);

    document.getElementById('total').textContent=database.items.length;
    document.getElementById('week').textContent=database.items.filter(
      item=>new Date(item.date)>=Date.now()-7*864e5
    ).length;
    document.getElementById('sourcesCount').textContent=sources.length;
    document.getElementById('competitorsCount').textContent=database.items.filter(
      item=>(item.competitors||[]).length
    ).length;

    const updated=database.updated_at
      ?new Date(database.updated_at).toLocaleString('ru-RU')
      :'ещё не запускался';

    const stats=database.stats
      ?` · источников: ${database.stats.sources_ok} успешно, ${database.stats.sources_warning} без материалов, ${database.stats.sources_failed} ошибок`
      :'';

    status.textContent='Обновлено: '+updated+stats;
    render();
  }catch(error){
    status.innerHTML=`<div class="error">Не удалось загрузить news.json: ${escapeHtml(error.message)}.</div>`;
    console.error(error);
  }
}

window.addEventListener('DOMContentLoaded',loadData);
