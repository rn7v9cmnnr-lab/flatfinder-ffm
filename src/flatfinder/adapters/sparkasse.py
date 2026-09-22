"""Sparkassen-Immobilien: first-party rental offers in Frankfurt's 10 km area.

Immowelt cooperation cards are intentionally excluded to avoid syndication duplicates.
"""
from __future__ import annotations
import json
from selectolax.parser import HTMLParser
from ..models import Kind, Listing
from .base import HttpAdapter, AdapterError

URL = 'https://immobilien.sparkasse.de/immobilien/treffer'
PARAMS = dict(estateTypeGroupingId=403, marketingType='rent', perimeter=10,
              sortBy='default_asc', usageType='residential',
              zipCityEstateId='50.11088/8.68243/1__Frankfurt am Main')

class SparkasseAdapter(HttpAdapter):
    source = 'sparkasse'
    min_interval = 2.0

    async def fetch(self):
        found = {}
        for page in range(1, 6):
            if page > 1:
                await self.polite_sleep()
            response = await self.get(URL, params={**PARAMS, 'page': page})
            payload = self.read_page(response.text)
            for listing in self.parse_items(payload['firstPageEstates']):
                found[listing.key] = listing
            if page >= payload['pageCount']:
                break
        return list(found.values())

    @staticmethod
    def read_page(html):
        node = HTMLParser(html).css_first('script#__NEXT_DATA__')
        if node is None:
            raise AdapterError('Sparkasse: Angebotsdaten fehlen')
        try:
            data = json.loads(node.text())['props']['pageProps']
            if not isinstance(data['firstPageEstates'], list) or not isinstance(data['pageCount'], int):
                raise ValueError('unexpected schema')
            return data
        except (KeyError, ValueError, TypeError) as exc:
            raise AdapterError('Sparkasse: Angebotsstruktur geändert') from exc

    @staticmethod
    def parse_items(items):
        out = []
        for item in items:
            if item.get('marketingType') != 'rent' or item.get('objectType') != 'flat':
                continue
            if not any(x.get('label') == 'Sparkassenangebot' for x in item.get('eyeCatcher', [])):
                continue
            if not item.get('id') or not item.get('title') or not item.get('subtitle'):
                raise AdapterError('Sparkasse: Pflichtfelder fehlen')
            facts = {x['name']: x.get('numeric') for x in item.get('mainFacts', [])}
            price = item.get('priceData') or {}
            out.append(Listing(source='sparkasse', source_id=str(item['id']), kind=Kind.PORTAL,
                title=item['title'], city=item['subtitle'],
                url='https://immobilien.sparkasse.de/expose/'+item['id']+'.html',
                price_cold=price.get('numeric') if price.get('name') == 'rentCold' else None,
                price_warm=price.get('numeric') if price.get('name') == 'rentWarm' else None,
                sqm=facts.get('livingSpace'), rooms=facts.get('roomNumber'),
                lat=item.get('lat'), lng=item.get('lng'), position_approx=True,
                image_url=(item.get('images') or [None])[0]))
        return out
