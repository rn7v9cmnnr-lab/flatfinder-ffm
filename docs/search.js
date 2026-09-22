/* Shared by the dashboard and the scheduled email search. No DOM dependencies. */
(function(root,factory){const api=factory();if(typeof module==="object"&&module.exports)module.exports=api;else root.FFSearch=api;})(typeof globalThis!=="undefined"?globalThis:this,function(){
"use strict";
function distanz(aLat,aLng,bLat,bLng){
  const R=6371, r=Math.PI/180;
  const dLat=(bLat-aLat)*r, dLng=(bLng-aLng)*r;
  const h=Math.sin(dLat/2)**2 + Math.cos(aLat*r)*Math.cos(bLat*r)*Math.sin(dLng/2)**2;
  return 2*R*Math.asin(Math.sqrt(h));
}

// Die Quellen liefern mal Kalt-, mal nur Warmmiete. Das darf die
// Oberflaeche nicht verwischen - sonst vergleicht man Aepfel mit Birnen.
function miete(l){
  if(l.price_cold!=null) return {wert:l.price_cold, art:"kalt", warm:false};
  if(l.price_warm!=null) return {wert:l.price_warm, art:"warm", warm:true};
  return {wert:null, art:"", warm:false};
}

function istNeu(l){
  return (Date.now() - new Date(l.first_seen).getTime()) < 36e5*24;
}

// Originaltitel und vorhandene Beschreibung prüfen, keine Score-Begründungen.
// Untermiete kann unbefristet sein und ist deshalb ein eigener Filter.
function ausschlussTreffer(l){
  const titel=String((l.title||"")+" "+(l.description||"")).normalize("NFKC").toLowerCase();
  const regeln={
    zeit:/\b(?:zwischenmiete|zwischenvermietung|befristet(?:e[rmns]?)?|zeitmiete|wohnen auf zeit|temporary rental|short[ -]term)\b/g,
    untermiete:/\b(?:untermiete|untervermietung|untermieter(?:in)?|sublet)\b/g,
    tausch:/\b(?:wohnungstausch|tauschwohnung|tauschangebot|wohnungstauschangebot|tausch gegen|nur (?:im )?tausch)\b/g
  };
  return Object.entries(regeln).filter(([,regex])=>[...titel.matchAll(regex)].some(m=>{
    const davor=titel.slice(0,m.index);
    // „Keine Zwischenmiete“, „nicht befristet“ und „ohne Wohnungstausch“ sind keine Treffer.
    return !/\b(?:kein(?:e[rmns]?)?|nicht|ohne)\s+(?:eine?\s+)?$/.test(davor);
  })).map(([key])=>key);
}

function merkmalTreffer(l){
  const text=[l.title,l.description].filter(Boolean).join(". ").normalize("NFKC").toLowerCase();
  const regeln={balkon:/\b(?:balkon\w*|terrasse\w*|loggia)\b/g,
    ebk:/\b(?:einbauküche\w*|ebk)\b/g,aufzug:/\b(?:aufzug\w*|aufzüge\w*|fahrstuhl\w*|personenaufzug\w*|lift)\b/g,
    garten:/\b(?:garten|gartennutzung|gartenanteil|gemeinschaftsgarten|privatgarten)\b/g,
    stellplatz:/\b(?:stellplatz\w*|stellplätze\w*|garage\w*|tiefgarage\w*|parkplatz\w*)\b/g,
    barrierefrei:/\bbarrierefrei\w*\b/g};
  return Object.entries(regeln).filter(([,r])=>[...text.matchAll(r)].some(m=>{
    const davor=text.slice(0,m.index), danach=text.slice(m.index+m[0].length);
    return !/\b(?:kein(?:e[rmns]?)?|ohne|nicht)\s+(?:(?:eigen\w*|privat\w*|groß\w*|klein\w*)\s+)?$/.test(davor)
      && !/^\s*(?::|ist)?\s*(?:nein|nicht vorhanden|nicht verfügbar)\b/.test(danach);
  })).map(([k])=>k);
}

function passt(l, f, hatMitte){
  if(l.gone) return false;
  if((f.merkmale||[]).some(k=>!merkmalTreffer(l).includes(k))) return false;
  if((f.ausschluss||[]).some(k=>ausschlussTreffer(l).includes(k))) return false;
  if(f.pmax){
    // Gegen die Kaltmiete pruefen, wo sie bekannt ist. Kennt die Quelle nur
    // die Warmmiete, waere ein direkter Vergleich unfair - dann grosszuegig
    // mit Aufschlag pruefen und das Angebot lieber zeigen als verstecken.
    const m = miete(l);
    if(m.wert==null) return false;
    const grenze = m.warm ? f.pmax*1.35 : f.pmax;
    if(m.wert > grenze) return false;
  }
  if(f.qmin && (l.sqm==null || l.sqm < f.qmin)) return false;
  if(f.rmin && (l.rooms==null || l.rooms < f.rmin)) return false;
  if(f.rmax && (l.rooms==null || l.rooms > f.rmax)) return false;
  if(f.anbieter && (l.kind||"sonstige") !== f.anbieter) return false;
  if(!f.quellen.includes(l.source)) return false;
  if(f.bezirke.length && !f.bezirke.includes(l.district || l.city || "?")) return false;
  if(f.aktualitaet){
    const alter=Date.now()-new Date(l.first_seen).getTime();
    if(!Number.isFinite(alter) || alter<0 || alter>f.aktualitaet*36e5) return false;
  }
  if(f.umkreis && hatMitte){
    // Der Mittelpunkt kann aus Kartenklick, PLZ ODER Auswahlliste kommen -
    // deshalb wird er uebergeben und hier nicht neu geraten. Genau daran
    // ist der PLZ-Umkreis zuerst gescheitert: die Pruefung fragte nur die
    // Auswahlliste ab, die bei PLZ-Eingabe leer ist.
    if(l._dist == null){
      // Ohne bekannte Lage laesst sich die Entfernung nicht pruefen. Wer
      // "2 km" einstellt, will keine Angebote sehen, die ueberall liegen
      // koennen - also raus, aber sichtbar zaehlbar und zuschaltbar.
      return false;
    }
    if(l._dist > f.umkreis) return false;
  }
  return true;
}


function matchesSaved(listing, search){
  const f=search.filters, center=search.center;
  const l={...listing,_dist:center&&listing.lat!=null&&listing.lng!=null?distanz(center[0],center[1],listing.lat,listing.lng):null};
  return passt(l,f,!!center);
}
return {distanz,miete,istNeu,ausschlussTreffer,merkmalTreffer,passt,matchesSaved};
});
