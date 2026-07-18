from __future__ import annotations
import hashlib, html, json, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import feedparser, requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent
CONFIG=json.loads((ROOT/"global_sources.json").read_text(encoding="utf-8"))
OUTPUT=ROOT/"global_news.json"
TZ=timezone(timedelta(hours=3))
SESSION=requests.Session()
SESSION.headers.update({"User-Agent":"Mozilla/5.0 (compatible; LevelGlobalIntelligence/1.0)"})

PROPERTY=["real estate","property","residential","development","developer","housing","apartment","office","mixed-use","branded residence","architecture","hospitality","homebuyer","luxury residence"]
LUXURY=["luxury","premium","affluent","wealthy","high-net-worth","hnwi","ultra-high-net-worth","exclusive","private client","concierge","bespoke","personalization","membership","private club","branded residence"]
MARKETING=["marketing","advertising","campaign","brand","customer experience","consumer","audience","crm","loyalty","content","media","digital","social","activation","partnership","collaboration","positioning","retargeting","personalization"]
RESEARCH=["research","report","survey","study","insight","trend","data","forecast","consumer behavior","customer journey","segmentation"]
PROPTECH=["proptech","smart building","digital twin","virtual tour","vr","ar","ai","artificial intelligence","platform","automation","building technology"]
ADTECH=["adtech","programmatic","retail media","connected tv","ctv","dooh","measurement","attribution","media buying","targeting","first-party data","privacy"]
ACTION=["launches","launch","introduces","unveils","campaign","partnership","collaboration","case study","strategy","experience","innovation","new format"]

def clean(v):
    return re.sub(r"\s+"," ",BeautifulSoup(html.unescape(v or ""),"html.parser").get_text(" ",strip=True)).strip()

def dt(entry):
    for key in ("published","updated","created"):
        value=getattr(entry,key,None)
        if value:
            try:
                d=parsedate_to_datetime(value)
                return d.astimezone(TZ) if d.tzinfo else d.replace(tzinfo=TZ)
            except Exception: pass
    return datetime.now(TZ)

def count(words,text): return sum(1 for w in words if w in text)

def applications(category,text):
    if category=="Luxury":
        return ["Выделить механику клубности, персонального сервиса или ограниченного доступа.","Адаптировать подход для премиальных проектов и CRM-коммуникаций Level.","Проверить формат закрытого события, партнёрства или concierge-сервиса."]
    if category=="Developers":
        return ["Сравнить позиционирование и презентацию продукта с проектами Level.","Проверить применимость формата шоурума, контента или клиентского маршрута.","Использовать находку при разработке концепции следующей кампании."]
    if category=="Research":
        return ["Сверить выводы с CRM, Метрикой и исследованиями Level.","Использовать релевантные данные при сегментации и защите стратегии.","Проверить гипотезу на российской аудитории небольшим исследованием."]
    if category=="PropTech":
        return ["Оценить влияние технологии на путь клиента и работу отдела продаж.","Проверить возможность пилота на одном проекте или в одном офисе продаж.","Задать KPI: вовлечение, конверсия, скорость принятия решения или качество лида."]
    if category=="AdTech":
        return ["Проверить доступность технологии у российских площадок и партнёров.","Сформировать ограниченный медиатест с контрольной группой.","Измерять не только клики, но и визиты, брендовый поиск и post-view эффект."]
    return ["Выделить механику без привязки к зарубежному рынку.","Определить подходящий проект, аудиторию и этап воронки.","Собрать быстрый прототип и заранее определить KPI."]

def make_item(row,source):
    title=clean(row.get("title","")); summary=clean(row.get("summary",""))
    text=(title+" "+summary).lower()
    p=count(PROPERTY,text); l=count(LUXURY,text); m=count(MARKETING,text)
    r=count(RESEARCH,text); pt=count(PROPTECH,text); a=count(ADTECH,text); action=count(ACTION,text)
    category=source["category"]
    category_signal={"Developers":p+m,"Luxury":l+m,"Research":r+m,"Marketing":m,"PropTech":pt+p,"AdTech":a+m}.get(category,m)
    score=category_signal*12+action*7+(6 if source.get("tier")==1 else 2)
    # Broad enough for specialist sources, but remove clearly irrelevant pieces.
    if score<22 and not (category=="Luxury" and l>=1) and not (category=="Research" and r>=1):
        return None
    if category=="Luxury" and l==0 and m==0 and p==0: return None
    if category=="Developers" and p==0: return None
    if category=="AdTech" and a==0 and m<2: return None
    if category=="PropTech" and pt==0 and p==0: return None

    potential=5 if score>=75 else 4 if score>=52 else 3 if score>=34 else 2
    relevance="Высокая" if score>=70 or (source.get("tier")==1 and score>=48) else "Средняя" if score>=38 else "Низкая"
    signal={"Luxury":"Luxury-практика","Developers":"Девелоперский кейс","Research":"Исследование","Marketing":"Маркетинговый кейс","PropTech":"PropTech","AdTech":"Рекламная технология"}.get(category,"Мировая практика")
    value={
      "Luxury":"Материал показывает, как премиальные бренды и проекты работают с состоятельной аудиторией через сервис, персонализацию, эксклюзивность и клиентский опыт.",
      "Developers":"Материал показывает зарубежный подход к продукту, брендингу, продажам или презентации девелоперского проекта.",
      "Research":"Исследование может дать новые ориентиры по поведению аудитории, клиентскому пути, спросу и коммуникации.",
      "Marketing":"Механику кампании можно рассмотреть как источник идей для бренда, контента, CRM или медиамикса Level.",
      "PropTech":"Технология может улучшить клиентский путь, дистанционные продажи, презентацию продукта или операционные процессы.",
      "AdTech":"Инструмент или формат может расширить медиамикс и улучшить таргетинг, измерение или работу с данными."
    }.get(category,"Зарубежный материал содержит потенциально применимую практику.")
    return {
      "id":hashlib.sha1(row["url"].encode()).hexdigest()[:16],
      "date":row["published"].date().isoformat(),
      "source":source["name"],"source_tier":source.get("tier",3),
      "title":title,"url":row["url"],"summary":summary[:700] or title,
      "category":category,"region":source.get("region","Global"),
      "relevance_score":score,"relevance_label":relevance,
      "potential":potential,"signal_type":signal,
      "level_value":value,"level_applications":applications(category,text)
    }

def collect(source):
    rows=[]
    for feed_url in source.get("feeds",[]):
        try:
            feed=feedparser.parse(feed_url,request_headers={"User-Agent":SESSION.headers["User-Agent"]})
            for e in feed.entries[:CONFIG.get("items_per_feed",45)]:
                link=getattr(e,"link","").split("#")[0]
                title=clean(getattr(e,"title",""))
                summary=clean(getattr(e,"summary","") or getattr(e,"description",""))
                if link and title: rows.append({"url":link,"title":title,"summary":summary,"published":dt(e)})
            if rows: break
        except Exception: pass
    items=[x for x in (make_item(row,source) for row in rows) if x]
    return source["name"],items

def existing():
    try:
        d=json.loads(OUTPUT.read_text(encoding="utf-8"))
        return d if isinstance(d,dict) else {"items":d}
    except Exception: return {"items":[]}

def main():
    old=existing(); by_url={i["url"]:i for i in old.get("items",[]) if i.get("url")}
    status={}; ok=warning=failed=0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures=[ex.submit(collect,s) for s in CONFIG["sources"]]
        for f in as_completed(futures):
            try:
                name,items=f.result()
                for item in items: by_url[item["url"]]=item
                status[name]=f"ok · {len(items)}" if items else "warning · 0"
                ok+=bool(items); warning+=not bool(items)
                print(name,status[name],flush=True)
            except Exception as e:
                failed+=1; print("error",e,flush=True)
    cutoff=(datetime.now(TZ)-timedelta(days=CONFIG.get("retention_days",365))).date().isoformat()
    rows=[i for i in by_url.values() if i.get("date","")>=cutoff]
    seen=set(); result=[]
    for item in sorted(rows,key=lambda x:(x.get("date",""),x.get("potential",0),x.get("relevance_score",0)),reverse=True):
        key=re.sub(r"\W+","",item.get("title","").lower())[:160]
        if key in seen: continue
        seen.add(key); result.append(item)
    payload={"updated_at":datetime.now(TZ).isoformat(timespec="seconds"),"stats":{"sources_ok":ok,"sources_warning":warning,"sources_failed":failed},"source_status":status,"items":result[:CONFIG.get("max_items",500)]}
    OUTPUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print("Saved",len(payload["items"]),flush=True)

if __name__=="__main__": main()
