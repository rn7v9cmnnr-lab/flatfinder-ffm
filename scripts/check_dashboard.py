"""Browser regression checks for the static dashboard (local data, real Leaflet)."""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width':1280,'height':1200})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    def serve(route):
        path = route.request.url.split('flatfinder.test/',1)[1].split('?',1)[0]
        file = root / 'docs' / (path or 'index.html')
        route.fulfill(path=str(file))
    if '--live' not in sys.argv:
        page.route('https://flatfinder.test/**', serve)
    page.goto('https://rn7v9cmnnr-lab.github.io/flatfinder-ffm/?view=split' if '--live' in sys.argv else 'https://flatfinder.test/')
    page.wait_for_function('ALLE.length > 0 && typeof L !== "undefined"')
    page.locator('#plz').fill('60311')
    assert page.locator('#karte').is_visible()
    assert page.locator('#tabelle').is_visible()
    table_box = page.locator('.listenbereich').bounding_box()
    map_box = page.locator('.kartenbereich').bounding_box()
    assert table_box['x'] < map_box['x'] and abs(table_box['y']-map_box['y']) < 2
    page.locator('#anbieter').select_option('grossvermieter')
    assert page.evaluate('ALLE.filter(l=>passt(l,filterLesen(),true)).every(l=>l.kind === "grossvermieter")')
    page.locator('#anbieter').select_option('genossenschaft')
    assert page.evaluate('ALLE.filter(l=>passt(l,filterLesen(),true)).every(l=>l.kind === "genossenschaft")')
    assert page.locator('#karte').is_visible()
    assert 'Angebote' in page.locator('#coopstand').text_content()
    page.locator('#anbieter').select_option('')
    assert page.locator('#umkreis').input_value() == '3'
    assert page.evaluate('MAP.getCenter().distanceTo(L.latLng(PLZ_POS["60311"])) < 100')
    assert page.evaluate('KREIS.getRadius()') == 3000
    page.locator('#umkreis').fill('1')
    assert page.evaluate('KREIS.getRadius()') == 1000
    assert page.evaluate('ALLE.filter(l=>passt(l,filterLesen(),true)).every(l=>l._dist <= 1)')
    page.locator('#mitte').select_option('50.1204,8.6520')
    assert page.locator('#plz').input_value() == ''
    assert page.evaluate('MAP.getCenter().distanceTo(L.latLng(50.1204,8.6520)) < 100')
    page.evaluate('MAP.setZoom(16, {animate:false})')
    page.locator('#karte').click(position={'x':80,'y':80})
    assert page.evaluate('MAP.getZoom()') == 16
    assert page.locator('#mitte').input_value() == '50.1204,8.6520'
    page.locator('#karte').dblclick(position={'x':80,'y':80})
    page.wait_for_function('MAP.getZoom() === 17')
    page.wait_for_timeout(300)
    assert page.evaluate('KLICK_MITTE === null')
    page.evaluate('zeichnen()')
    assert page.evaluate('MAP.getZoom()') == 17
    page.locator('#ansicht').click()
    page.locator('#ansicht').click()
    assert page.evaluate('MAP.getZoom()') == 17
    page.locator('#pmax').fill('1500')
    assert page.evaluate('MAP.getZoom()') == 17
    page.locator('#pmax').fill('')
    page.locator('#mittelpunktSetzen').click()
    page.evaluate('MAP.fire("click", {latlng:L.latLng(50.1,8.7)})')
    assert page.evaluate('MAP.getZoom()') == 17
    assert page.locator('#mittelpunktSetzen').get_attribute('aria-pressed') == 'false' 
    assert page.evaluate('mittelpunkt(filterLesen())[0]') == 50.1
    page.locator('#plz').fill('60311')
    page.evaluate('MAP.panTo([50.15,8.75], {animate:false})')
    page.wait_for_timeout(150)
    center = page.evaluate('MAP.getCenter()')
    page.locator('#qmin').fill('100000')
    assert page.evaluate('(c) => MAP.project(MAP.getCenter()).distanceTo(MAP.project(L.latLng(c.lat,c.lng))) <= 1', center), (center, page.evaluate('MAP.getCenter()'), page.evaluate('KARTENBEREICH'))
    page.locator('#suchgebiet').click()
    assert page.evaluate('MAP.getCenter().distanceTo(L.latLng(PLZ_POS["60311"])) < 100')
    assert page.evaluate('KREIS.getRadius()') == 1000
    page.locator('#qmin').fill('')
    page.locator('#umkreis').fill('')
    assert page.evaluate('KREIS === null')
    assert page.evaluate('MAP.getCenter().distanceTo(L.latLng(PLZ_POS["60311"])) < 100')
    page.locator('#plz').fill('99999')
    assert page.locator('#plz').get_attribute('aria-invalid') == 'true'
    assert page.evaluate('mittelpunkt(filterLesen()) === null')
    page.locator('#plz').fill('60311')
    page.reload()
    page.wait_for_function('MAP !== null && KREIS !== null')
    assert page.locator('#plz').input_value() == '60311'
    page.wait_for_function('Array.from(document.querySelectorAll(".leaflet-tile")).some(t=>t.complete && t.naturalWidth > 0)', timeout=30000)
    page.evaluate('window.scrollTo(0,0)')
    page.screenshot(path=str(root / 'map-desktop.jpg'), quality=55)
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#suchgebiet').click()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('#tabelle').is_visible()
    page.screenshot(path=str(root / 'map-mobile.jpg'), quality=55)
    page.locator('#reset').click()
    assert page.evaluate('KREIS === null && MITTENMARKER === null')
    # List/marker selection is one shared accordion, without changing the search centre.
    page.set_viewport_size({'width':1280,'height':1200})
    page.locator('#suchgebiet').click()
    first=page.evaluate('ALLE.find(l=>ANGEBOT_MARKER.has(l.key))')
    row_id=page.evaluate('(key)=>ZEILEN.get(key).id',first['key'])
    toggle=page.locator('[id="'+row_id+'"]').locator('.listing-toggle')
    before=page.evaluate('JSON.stringify(mittelpunkt(filterLesen()))')
    toggle.click()
    assert toggle.get_attribute('aria-expanded') == 'true'
    assert page.locator('.listing-details').count() == 1
    assert page.locator('.marker.selected').count() == 1
    assert page.evaluate('(l)=>MAP.getCenter().distanceTo(L.latLng(l.lat,l.lng))<30',first)
    zoom=page.evaluate('MAP.getZoom()')
    toggle.click()
    assert page.locator('.listing-details').count() == 0
    assert page.evaluate('MAP.getZoom()') == zoom
    toggle.press('Enter')
    assert page.locator('.listing-details').count() == 1
    second=page.evaluate('(key)=>ALLE.find(l=>l.key!==key && ANGEBOT_MARKER.has(l.key) && ALLE.filter(o=>ANGEBOT_MARKER.has(o.key) && Math.abs(o.lat-l.lat)+Math.abs(o.lng-l.lng)<0.001).length===1)',first['key'])
    page.evaluate('(l)=>MAP.setView([l.lat,l.lng],15,{animate:false})',second)
    marker_id=page.evaluate('(key)=>{const e=ANGEBOT_MARKER.get(key).getElement();e.id="test-marker";return e.id}',second['key'])
    page.locator('#test-marker').click()
    assert page.evaluate('AUSWAHL') == second['key']
    assert page.locator('.listing-details').count() == 1
    assert page.evaluate('JSON.stringify(mittelpunkt(filterLesen()))') == before
    page.locator('.auf-karte').click()
    page.screenshot(path=str(root/'selected-desktop.jpg'),quality=55)
    page.locator('.details-schliessen').click()
    assert page.locator('.listing-details').count() == 0
    toggle.click()
    page.locator('#qmin').fill('100000')
    assert page.evaluate('AUSWAHL === null')
    assert page.locator('.marker.selected').count() == 0
    page.locator('#qmin').fill('')
    # Unknown positions must never point to an unrelated apartment.
    page.evaluate('ALLE.unshift({key:"test-unknown",title:"Test ohne Lage",source:ALLE[0].source,kind:"portal",score:50});zeichnen()')
    page.locator('#angebot-test-unknown .listing-toggle').click()
    assert 'Keine Lage bekannt' in page.locator('.listing-details').inner_text()
    assert page.locator('.marker.selected').count() == 0
    assert page.locator('.auf-karte').count() == 0
    page.locator('.details-schliessen').click()
    toggle.click()
    page.set_viewport_size({'width':390,'height':844})
    page.locator('.auf-karte').click()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(root/'selected-mobile.jpg'),quality=55)
    # Keyword exclusions: separate subletting from time-limited rent; respect negation.
    cases=[('Zwischenmiete ab Oktober',['zeit']),('Befristete Wohnung',['zeit']),
           ('Wohnen auf Zeit',['zeit']),('Unbefristete Wohnung',[]),('Nicht befristet',[]),
           ('Keine Zwischenmiete',[]),('Keine befristete Untermiete',['untermiete']),
           ('Untermiete unbefristet',['untermiete']),('Wohnungstausch',['tausch']),
           ('Kein Wohnungstausch',[]),('Keine Zwischenmiete, aber befristet',['zeit'])]
    for title,wanted in cases:
        assert page.evaluate('(title)=>ausschlussTreffer({title})',title)==wanted, title
    ranged={"title":"Helle Wohnung", "description":"Befristete Mietzeit: 01.10.2026 bis 31.03.2027."}
    assert page.evaluate('(l)=>ausschlussTreffer(l)',ranged)==['zeit']
    assert page.evaluate('(l)=>!FFSearch.matchesSaved({...l,source:"wggesucht"},{filters:{quellen:["wggesucht"],bezirke:[],ausschluss:["zeit"]},center:null})',ranged)
    page.locator('#reset').click()
    page.evaluate('ALLE.unshift({key:"test-temporary",title:"Zwischenmiete Test",source:ALLE[0].source,kind:"portal",score:50});zeichnen()')
    check=page.locator('.ausschluss[value="zeit"]')
    check.check()
    assert check.evaluate("e=>getComputedStyle(e,'::after').content").strip('"') == "×"
    assert page.evaluate('(ausschlussTreffer({title:"Wohnung",description:"Nur Zwischenmiete"})).includes("zeit")')
    assert page.locator('#angebot-test-temporary').count()==0
    assert page.evaluate('filterLesen().ausschluss.includes("zeit")')
    page.reload()
    page.wait_for_function('ALLE.length > 0')
    assert check.is_checked()
    assert page.evaluate('ALLE.filter(l=>passt(l,filterLesen(),!!mittelpunkt(filterLesen()))).every(l=>!ausschlussTreffer(l).includes("zeit"))')
    page.locator('#reset').click()
    assert not check.is_checked()
    assert page.locator('.feinfilter').count()==0
    assert page.locator('#aktualitaet').is_visible()
    sources=page.locator('#quellen input:not(:disabled)')
    assert sources.count()>=5
    for checkbox in sources.all(): checkbox.uncheck()
    assert page.locator('#anzahl').inner_text()=='0'
    page.reload()
    page.wait_for_function('ALLE.length>0')
    assert page.locator('#quellen input:checked').count()==0
    page.locator('#quellen input[value="vonovia"]').check()
    assert page.evaluate('ALLE.filter(l=>passt(l,filterLesen(),false)).every(l=>l.source==="vonovia")')
    assert page.locator('#quellen input[value="immoscout"]').is_disabled()
    page.locator('[name=aktualitaet][value="24"]').check()
    assert page.evaluate('ALLE.filter(l=>passt(l,filterLesen(),false)).every(l=>Date.now()-new Date(l.first_seen).getTime()<=86400000)')
    page.locator('#reset').click()
    assert page.locator('#quellen input:checked').count()==sources.count()
    assert page.locator('[name=aktualitaet][value=""]').is_checked()
    assert page.locator('#suche').count()==0
    for title,wanted in [('Mit Balkon und EBK',['balkon','ebk']),('Ohne Balkon',[]),('Kein eigener Garten',[]),('Balkon: nein',[]),('Nicht barrierefrei',[]),('Gartenwohnung',[])]:
        assert page.evaluate('(title)=>merkmalTreffer({title})',title)==wanted,title
    assert page.evaluate('merkmalTreffer({description:"Terrasse und Aufzug"})')==['balkon','aufzug']
    page.locator('.merkmal[value="balkon"]').check()
    page.locator('.merkmal[value="ebk"]').check()
    assert page.evaluate('ALLE.filter(l=>passt(l,filterLesen(),false)).every(l=>["balkon","ebk"].every(k=>merkmalTreffer(l).includes(k)))')
    page.reload();page.wait_for_function('ALLE.length>0')
    assert page.locator('.merkmal:checked').count()==2
    page.locator('#reset').click()
    assert page.locator('.merkmal:checked').count()==0
    page.locator('.merkmal[value="balkon"]').check()
    page.evaluate('MAP.setView([50.12,8.68],15,{animate:false})')
    stamp=page.locator('#stand').inner_text()
    assert 'Letzter Suchlauf:' in stamp and 'Uhr' in stamp
    page.locator('#aktualisieren').click()
    page.wait_for_function('document.getElementById("aktualisieren").getAttribute("aria-busy")==="false"')
    assert page.locator('.merkmal[value="balkon"]').is_checked()
    assert page.evaluate('MAP.getZoom()')==15
    assert 'neuesten verfügbaren Stand' in page.locator('#refreshstatus').inner_text()
    page.route('**/data/listings.json?*',lambda route:route.fulfill(status=503,body='unavailable'))
    page.locator('#aktualisieren').click()
    page.wait_for_function('document.getElementById("refreshstatus").textContent.includes("fehlgeschlagen")')
    assert page.locator('#stand').inner_text()==stamp
    assert page.evaluate('ALLE.length>0')
    assert page.locator('#aktualisieren').is_enabled()
    assert not errors, errors
    browser.close()
print('PASS: PLZ, radius, place precedence, map click, pan preservation, zero results, no radius, invalid PLZ, reload, mobile, reset; no JS errors')
