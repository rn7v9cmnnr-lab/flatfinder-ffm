"""Browser checks for saved searches and local application drafts. No messages sent."""
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[1]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='msedge',headless=True)
    page=browser.new_page(viewport={'width':1400,'height':1050})
    errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    if '--live' not in sys.argv:
        def serve(route):
            path=route.request.url.split('flatfinder.test/',1)[1].split('?',1)[0]
            route.fulfill(path=str(root/'docs'/(path or 'index.html')))
        page.route('https://flatfinder.test/**',serve)
    page.goto('https://rn7v9cmnnr-lab.github.io/flatfinder-ffm/' if '--live' in sys.argv else 'https://flatfinder.test/')
    page.wait_for_function('ALLE.length>0')
    page.locator('#pmax').fill('1400')
    page.locator('#rmin').fill('2')
    expected=page.locator('#anzahl').inner_text()
    page.locator('#suchname').fill('Unser Zuhause')
    page.locator('#suche-speichern').click()
    assert page.locator('#bereich-studio').is_visible()
    assert not page.locator('#bereich-suche').is_visible()
    assert page.locator('.auftrag .quiet-label').inner_text()==expected+' Treffer'
    assert page.locator('#vorschau-angebot option').count()==int(expected)
    assert page.locator('#entwurf-kopieren').is_disabled()
    page.locator('#profil-name').fill('Testperson')
    page.locator('#profil-vorstellung').fill('Wir sind zwei Personen. <script>notExecuted()</script>')
    page.locator('#profil-einzug').fill('ab November')
    page.locator('#alarm-email').fill('private-example@example.org')
    assert page.locator('#entwurf-kopieren').is_enabled()
    assert 'Testperson' in page.locator('#entwurf-text').inner_text()
    assert '<script>notExecuted()</script>' in page.locator('#entwurf-text').inner_text()
    assert page.locator('#entwurf-text script').count()==0
    assert '{{wohnung}}' not in page.locator('#entwurf-text').inner_text()
    assert page.locator('#entwurf-original').get_attribute('href').startswith('https://')
    page.locator('.setup-details summary').click()
    with page.expect_download() as dl:
        page.locator('#auftraege-export').click()
    data=Path(dl.value.path()).read_text(encoding='utf-8')
    assert 'private-example' not in data and 'Testperson' not in data
    assert json.loads(data)['searches'][0]['filters']['pmax']==1400
    page.reload();page.wait_for_function('ALLE.length>0')
    assert page.locator('#bereich-studio').is_visible()
    assert page.locator('#profil-name').input_value()=='Testperson'
    page.locator('.auftrag button').filter(has_text='In Suche öffnen').click()
    assert page.locator('#pmax').input_value()=='1400'
    page.locator('#pmax').fill('900')
    page.locator('#tab-studio').click()
    assert page.locator('.auftrag .quiet-label').inner_text()==expected+' Treffer'
    page.locator('#profil-vorstellung').fill('Wir suchen zu zweit eine Wohnung in Frankfurt und freuen uns darauf, unser neues Zuhause kennenzulernen.')
    page.evaluate('window.scrollTo(0,0)')
    page.screenshot(path=str(root/'studio-desktop.jpg'),quality=60)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(root/'studio-mobile.jpg'),quality=60)
    page.locator('#studio-loeschen').click()
    assert page.locator('.auftrag').count()==0
    assert page.locator('#profil-name').input_value()==''
    assert page.locator('#entwurf-kopieren').is_disabled()
    assert not errors,errors
    browser.close()
print('PASS: tabs, saved filter snapshot, matching preview, personal template, escaping, export privacy, reload, mobile, delete')
