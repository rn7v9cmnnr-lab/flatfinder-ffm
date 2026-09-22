"""Browser regression checks for the static dashboard (local data, real Leaflet)."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page(viewport={'width':1280,'height':1000})
    errors = []
    page.on('pageerror', lambda e: errors.append(str(e)))
    def serve(route):
        path = route.request.url.split('flatfinder.test/',1)[1].split('?',1)[0]
        file = root / 'docs' / (path or 'index.html')
        route.fulfill(path=str(file))
    page.route('https://flatfinder.test/**', serve)
    page.goto('https://flatfinder.test/')
    page.wait_for_function('ALLE.length > 0 && typeof L !== "undefined"')
    page.locator('#plz').fill('60311')
    assert page.locator('#karte').is_visible()
    assert page.locator('#umkreis').input_value() == '3'
    assert page.evaluate('MAP.getCenter().distanceTo(L.latLng(PLZ_POS["60311"])) < 100')
    assert page.evaluate('KREIS.getRadius()') == 3000
    page.locator('#umkreis').fill('1')
    assert page.evaluate('KREIS.getRadius()') == 1000
    assert page.evaluate('ALLE.filter(l=>passt(l,filterLesen(),true)).every(l=>l._dist <= 1)')
    page.locator('#mitte').select_option('50.1204,8.6520')
    assert page.locator('#plz').input_value() == ''
    assert page.evaluate('MAP.getCenter().distanceTo(L.latLng(50.1204,8.6520)) < 100')
    page.evaluate('MAP.fire("click", {latlng:L.latLng(50.1,8.7)})')
    assert page.evaluate('mittelpunkt(filterLesen())[0]') == 50.1
    page.locator('#plz').fill('60311')
    page.evaluate('MAP.panTo([50.15,8.75], {animate:false})')
    page.wait_for_timeout(150)
    center = page.evaluate('MAP.getCenter()')
    page.locator('#suche').fill('unlikely-no-results-xyz')
    assert page.evaluate('(c) => MAP.getCenter().distanceTo(L.latLng(c.lat,c.lng)) < 1', center), (center, page.evaluate('MAP.getCenter()'), page.evaluate('KARTENBEREICH'))
    page.locator('#suchgebiet').click()
    assert page.evaluate('MAP.getCenter().distanceTo(L.latLng(PLZ_POS["60311"])) < 100')
    assert page.evaluate('KREIS.getRadius()') == 1000
    page.locator('#suche').fill('')
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
    page.screenshot(path=str(root / 'map-desktop.png'), full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.locator('#suchgebiet').click()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(root / 'map-mobile.png'), full_page=True)
    page.locator('#reset').click()
    assert page.evaluate('KREIS === null && MITTENMARKER === null')
    assert not errors, errors
    browser.close()
print('PASS: PLZ, radius, place precedence, map click, pan preservation, zero results, no radius, invalid PLZ, reload, mobile, reset; no JS errors')
