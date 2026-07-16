let database={items:[]};

const normalize=value=>(value||'').toString().toLowerCase();

const escapeHtml=value=>(value||'').toString().replace(/[&<>"']/g,char=>({
  '&':'&amp;',
  '<':'&lt;',
  '>':'&gt;',
  '"':'&quot;',
  "'":'&#039;'
}[char]));

function renderCard(item){
  const date=new Date(item.date+'T12:00:00').toLocaleDateString('ru-RU');
  const competitorTags=(item.competitors||[])
    .map(value=>`<span class="tag">${escapeHtml(value)}</span>`)
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
      ${competitorTags}
    </div>

    <div class="foot">
      <span>Важность ${Number(item.importance||0)}%</span>
      <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">
        Открыть →
      </a>
    </div>
  </article>`;
}

function fillSelect(id,values){
  const element=document.getElementById(id);

  values
    .sort()
    .forEach(value=>{
      element.insertAdjacentHTML(
        'beforeend',
        `<option>${escapeHtml(value)}</option>`
      );
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
        item.title,
        item.summary,
        item.source,
        item.topic,
        ...(item.competitors||[])
      ].join(' '));

      return (!text||haystack.includes(text))
        &&(!source||item.source===source)
        &&(!topic||item.topic===topic)
        &&(!competitor||(item.competitors||[]).includes(competitor));
    })
    .sort((a,b)=>{
      return (b.date||'').localeCompare(a.date||'')
        ||(b.importance||0)-(a.importance||0);
    });

  document.getElementById('grid').innerHTML=rows.length
    ?rows.map(renderCard).join('')
    :'<div class="empty">По выбранным фильтрам новостей нет.</div>';
}

fetch('./news.json?v='+Date.now())
  .then(response=>{
    if(!response.ok){
      throw new Error('HTTP '+response.status);
    }

    return response.json();
  })
  .then(data=>{
    database=Array.isArray(data)?{items:data}:data;
    database.items=database.items||[];

    const sources=[
      ...new Set(database.items.map(item=>item.source).filter(Boolean))
    ];

    const topics=[
      ...new Set(database.items.map(item=>item.topic).filter(Boolean))
    ];

    const competitors=[
      ...new Set(database.items.flatMap(item=>item.competitors||[]))
    ];

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
      ?` · запросов успешно: ${database.stats.queries_ok}, ошибок: ${database.stats.queries_failed}`
      :'';

    document.getElementById('status').textContent=
      'Обновлено: '+updated+stats;

    render();
  })
  .catch(error=>{
    document.getElementById('status').innerHTML=
      `<div class="error">Не удалось загрузить news.json: ${escapeHtml(error.message)}.</div>`;

    console.error(error);
  });
