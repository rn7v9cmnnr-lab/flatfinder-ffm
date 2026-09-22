/* Local draft workspace: no credentials, no network delivery, no auto applications. */
const STUDIO_KEY='flatfinder.studio.v1';
const STANDARD_BETREFF='Interesse an Ihrer Wohnung: {{wohnung}}';
const STANDARD_TEXT='Guten Tag,\n\nIhre Wohnung „{{wohnung}}“ in {{ort}} hat mein Interesse geweckt. Ich würde sie gern persönlich kennenlernen.\n\n{{vorstellung}}\n\n{{einzug}}\n\nÜber einen Besichtigungstermin würde ich mich freuen. Bei Fragen zu mir oder zu benötigten Unterlagen melde ich mich gern zurück.\n\nFreundliche Grüße\n{{name}}';
let studio={searches:[],email:'',name:'',intro:'',move:'',subject:STANDARD_BETREFF,body:STANDARD_TEXT};
try{const saved=JSON.parse(localStorage.getItem(STUDIO_KEY)||'null');if(saved&&Array.isArray(saved.searches))studio={...studio,...saved};}catch(e){}
let studioSearch='',studioListing='';
const studioFields={'alarm-email':'email','profil-name':'name','profil-einzug':'move','profil-vorstellung':'intro','bewerbung-betreff':'subject','bewerbung-text':'body'};
function studioSave(){
  try{localStorage.setItem(STUDIO_KEY,JSON.stringify(studio));return true;}
  catch(e){el('studio-status').textContent='Speichern in diesem Browser nicht möglich. Bitte Texte vor dem Schließen kopieren.';return false;}
}
function studioTab(tab){
  const on=tab==='studio';
  el('bereich-suche').hidden=on;el('bereich-studio').hidden=!on;
  for(const key of ['suche','studio']){const active=key===tab;el('tab-'+key).setAttribute('aria-selected',String(active));el('tab-'+key).tabIndex=active?0:-1;}
  history.replaceState(null,'',on?'#automatisierung':location.pathname+location.search);
  window.scrollTo(0,0);
  if(on)studioRender();else if(MAP)requestAnimationFrame(()=>MAP.invalidateSize({pan:false}));
}
for(const key of ['suche','studio']){
  el('tab-'+key).onclick=()=>studioTab(key);
  el('tab-'+key).onkeydown=e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const target=e.key==='Home'?'suche':e.key==='End'?'studio':key==='suche'?'studio':'suche';studioTab(target);el('tab-'+target).focus();}};
}
el('zur-suche').onclick=()=>{studioTab('suche');el('suchname').focus();};
function searchSummary(search){
  const f=search.filters,parts=[];
  if(f.pmax)parts.push('bis '+eur(f.pmax)+' kalt');if(f.qmin)parts.push('ab '+f.qmin+' m²');
  if(f.rmin||f.rmax)parts.push((f.rmin||'1')+'–'+(f.rmax||'∞')+' Zimmer');
  if(search.center&&f.umkreis)parts.push(f.umkreis+' km'+(f.plz?' um '+f.plz:''));
  if(f.bezirke?.length)parts.push(f.bezirke.join(', '));
  if(f.merkmale?.length)parts.push(f.merkmale.map(k=>({balkon:'Balkon/Terrasse',ebk:'Einbauküche',aufzug:'Aufzug',garten:'Garten',stellplatz:'Stellplatz/Garage',barrierefrei:'Barrierefrei'}[k])).join(', '));
  if(f.ausschluss?.length)parts.push('ohne '+f.ausschluss.map(k=>({zeit:'Zwischenmiete',untermiete:'Untermiete',tausch:'Tausch'}[k])).join(', '));
  if(f.aktualitaet)parts.push('neu in '+f.aktualitaet+' Stunden');
  parts.push((f.quellen||[]).map(quellenName).join(', ')||'Keine Quellen');
  if(f.anbieter)parts.push(ART[f.anbieter]||f.anbieter);
  return parts.join(' · ');
}
function studioMatches(search){return ALLE.filter(l=>FFSearch.matchesSaved(l,search));}
el('suche-speichern').onclick=()=>{
  if(!ALLE.length){el('studio-status').textContent='Bitte warten, bis die Angebote geladen sind.';return;}
  if(studio.searches.length>=10){studioTab('studio');el('studio-status').textContent='Du kannst bis zu zehn Suchaufträge speichern.';return;}
  const f=filterLesen(),center=mittelpunkt(f);
  if((f.plz||f.umkreis)&&!center){el('umkreishinweis').textContent='Vor dem Speichern bitte eine gültige PLZ, einen Ort oder einen Kartenpunkt wählen.';el('plz').focus();return;}
  const search={id:crypto.randomUUID(),name:el('suchname').value.trim()||'Meine Suche '+(studio.searches.length+1),filters:JSON.parse(JSON.stringify(f)),center:center?[...center]:null,emailRequested:true};
  studio.searches.push(search);studioSearch=search.id;const stored=studioSave();studioTab('studio');if(stored)el('studio-status').textContent='Suchauftrag lokal gespeichert. E-Mail-Versand ist noch nicht eingerichtet.';
};
function studioApply(search){
  HTMLFormElement.prototype.reset.call(el('filters'));KLICK_MITTE=null;filterSchreiben(search.filters);
  // Freeze the saved geographic center, even if the reference table changes.
  if(search.center)KLICK_MITTE=[...search.center];
  quellenAufbauen(search.filters);
  document.querySelectorAll('#quellen input').forEach(c=>c.checked=!c.disabled&&search.filters.quellen.includes(c.value));
  document.querySelectorAll('#bezirke .chip').forEach(c=>c.setAttribute('aria-pressed',String((search.filters.bezirke||[]).includes(c.dataset.v))));
  KARTE_AUSRICHTEN=true;zeichnen();studioTab('suche');
}
function studioRender(){
  el('suchauftraege').replaceChildren();
  if(!studio.searches.length){const p=document.createElement('p');p.className='studio-empty';p.textContent='Noch kein Suchauftrag. Stelle deine Filter in der Wohnungssuche ein und wähle „Suche speichern“.';el('suchauftraege').append(p);}
  for(const search of studio.searches){
    const box=document.createElement('article');box.className='auftrag';
    const head=document.createElement('div');head.className='auftrag-head';const name=document.createElement('b');name.textContent=search.name;const count=document.createElement('span');count.className='quiet-label';count.textContent=studioMatches(search).length+' Treffer';head.append(name,count);
    const summary=document.createElement('p');summary.textContent=searchSummary(search);
    const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=!!search.emailRequested;check.onchange=()=>{search.emailRequested=check.checked;studioSave();el('studio-status').textContent='E-Mail-Wunsch gespeichert. Kein Versanddienst verbunden.';};label.append(check,document.createTextNode('Für E-Mail-Benachrichtigungen vormerken'));
    const actions=document.createElement('div');actions.className='auftrag-actions';
    for(const [text,action] of [['In Suche öffnen',()=>studioApply(search)],['Vorschau',()=>{studioSearch=search.id;studioRender();el('vorschau-suche').focus();}],['Entfernen',()=>{studio.searches=studio.searches.filter(s=>s.id!==search.id);studioSave();studioRender();}]]){const button=document.createElement('button');button.type='button';button.textContent=text;button.onclick=action;actions.append(button);}
    box.append(head,summary,label,actions);el('suchauftraege').append(box);
  }
  const select=el('vorschau-suche');select.replaceChildren();
  for(const search of studio.searches)select.add(new Option(search.name,search.id));
  if(studio.searches.some(s=>s.id===studioSearch))select.value=studioSearch;
  studioSearch=select.value;studioPreview();
}
function studioText(template,listing){
  const values={wohnung:listing?.title||'[Wohnung auswählen]',ort:listing?.district||listing?.city||'[Ort]',name:studio.name.trim(),vorstellung:studio.intro.trim(),einzug:studio.move.trim()?'Als Einzugstermin würde für mich '+studio.move.trim()+' passen.':''};
  return template.replace(/\{\{(wohnung|ort|name|vorstellung|einzug)\}\}/g,(_,key)=>values[key]).replace(/\n{3,}/g,'\n\n').trim();
}
function studioPreview(){
  const search=studio.searches.find(s=>s.id===studioSearch),items=search?studioMatches(search):[];
  const select=el('vorschau-angebot');select.replaceChildren();items.forEach(l=>select.add(new Option(l.title,l.key)));
  if(items.some(l=>l.key===studioListing))select.value=studioListing;
  select.disabled=!items.length;studioListing=select.value;
  const listing=items.find(l=>l.key===studioListing);
  el('mail-vorschau').replaceChildren();
  const heading=document.createElement('b');heading.textContent=listing?'Passende Wohnung: '+listing.title:'Noch keine passende Wohnung ausgewählt';
  const facts=document.createElement('p');facts.textContent=listing?[listing.rooms?listing.rooms+' Zimmer':null,listing.sqm?listing.sqm+' m²':null,miete(listing).wert!=null?eur(miete(listing).wert)+' '+miete(listing).art:'Miete nicht angegeben',listing.district||listing.city].filter(Boolean).join(' · '):'Speichere eine Suche mit passenden Treffern, um eine echte Wohnung in der Vorschau zu sehen.';
  const note=document.createElement('p');note.textContent='E-Mail-Vorschau · nicht versendet'+(studio.email?' · an '+studio.email:'');el('mail-vorschau').append(note,heading,facts);
  el('entwurf-betreff').textContent=studioText(studio.subject,listing);el('entwurf-text').textContent=studioText(studio.body,listing);
  el('entwurf-kopieren').disabled=!listing||!studio.name.trim()||!studio.body.trim();
  const a=el('entwurf-original');let url;try{url=new URL(listing?.url);if(!['https:','http:'].includes(url.protocol))url=null;}catch(e){}a.hidden=!url;if(url)a.href=url.href;else a.removeAttribute('href');
}
el('vorschau-suche').onchange=()=>{studioSearch=el('vorschau-suche').value;studioListing='';studioPreview();};
el('vorschau-angebot').onchange=()=>{studioListing=el('vorschau-angebot').value;studioPreview();};
for(const [id,key] of Object.entries(studioFields)){el(id).value=studio[key]||'';el(id).oninput=()=>{studio[key]=el(id).value;studioSave();studioPreview();};}
el('vorlage-standard').onclick=()=>{studio.subject=STANDARD_BETREFF;studio.body=STANDARD_TEXT;el('bewerbung-betreff').value=studio.subject;el('bewerbung-text').value=studio.body;studioSave();studioPreview();};
el('entwurf-kopieren').onclick=async()=>{try{await navigator.clipboard.writeText(el('entwurf-betreff').textContent+'\n\n'+el('entwurf-text').textContent);el('studio-status').textContent='Bewerbung kopiert. Du kannst sie im Originalangebot einfügen.';}catch(e){el('studio-status').textContent='Kopieren nicht möglich. Bitte den Text in der Vorschau markieren und kopieren.';}};
el('auftraege-export').onclick=()=>{
  const config={version:1,channel:'email',searches:studio.searches.filter(s=>s.emailRequested).map(({id,name,filters,center})=>({id,name,filters,center}))};
  if(!config.searches.length){el('studio-status').textContent='Bitte mindestens einen Suchauftrag für E-Mail vormerken.';return;}
  const url=URL.createObjectURL(new Blob([JSON.stringify(config,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='flatfinder-suchauftraege.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  el('studio-status').textContent='Suchaufträge exportiert. Der Export aktiviert noch keinen Versand.';
};
el('studio-loeschen').onclick=()=>{studio={searches:[],email:'',name:'',intro:'',move:'',subject:STANDARD_BETREFF,body:STANDARD_TEXT};studioSave();for(const [id,key] of Object.entries(studioFields))el(id).value=studio[key]||'';studioRender();el('studio-status').textContent='Lokale Suchaufträge und persönliche Entwürfe gelöscht.';};
studioTab(location.hash==='#automatisierung'?'studio':'suche');
