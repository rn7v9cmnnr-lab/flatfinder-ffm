from pathlib import Path
from playwright.sync_api import sync_playwright
import sys
root=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
 b=p.chromium.launch(channel='msedge',headless=True);page=b.new_page(viewport={'width':1280,'height':1000});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 if '--live' not in sys.argv:
  def serve(route):
   path=route.request.url.split('flatfinder.test/',1)[1].split('?',1)[0];route.fulfill(path=str(root/'docs'/(path or 'index.html')))
  page.route('https://flatfinder.test/**',serve)
 page.goto('https://rn7v9cmnnr-lab.github.io/flatfinder-ffm/' if '--live' in sys.argv else 'https://flatfinder.test/');page.wait_for_function('ALLE.length>0')
 cases=[({'title':'WBS erforderlich'},['WBS nötig']),({'title':'Kein WBS erforderlich'},[]),({'title':'WBS nicht erforderlich'},[]),({'title':'Ideal für Studierende'},[]),({'title':'Nur für Studierende'},['Nur Studierende']),({'title':'Nicht nur für Studierende'},[]),({'title':'WBS erforderlich','wbs_required':False},[]),({'title':'Wohnung','wbs_required':True},['WBS nötig']),({'description':'Genossenschaftsanteile sind erforderlich'},['Genossenschaftsanteile']),({'title':'Wohnung','kind':'genossenschaft'},[])]
 for listing,wanted in cases:assert page.evaluate('(l)=>FFSearch.voraussetzungen(l).map(x=>x.label)',listing)==wanted,listing
 page.locator('#reset').click();page.evaluate('ALLE.unshift({key:"test-req",title:"Nur für Studierende",description:"Genossenschaftsanteile sind erforderlich",source:ALLE[0].source,kind:"portal",score:100,wbs_required:true});zeichnen()')
 row=page.locator('#angebot-test-req');assert row.locator('.voraussetzung').count()==3
 row.locator('.voraussetzung').first.click();assert row.locator('.voraussetzung-info').first.is_visible();assert page.locator('.listing-details').count()==0
 assert row.locator('.voraussetzung').first.get_attribute('title')
 row.locator('.voraussetzung').first.click();assert row.locator('.voraussetzung-info').first.is_hidden()
 page.set_viewport_size({'width':390,'height':844});row.locator('.voraussetzung').first.click();assert row.locator('.voraussetzung-info').first.is_visible();assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
 assert not errors,errors;b.close()
print('PASS: explicit requirements, negation, no inferred cooperative conditions, tap/hover details, mobile width, no unintended row activation')
