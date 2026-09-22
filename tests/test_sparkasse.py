import copy
import json
from pathlib import Path
import pytest
from flatfinder.adapters.sparkasse import SparkasseAdapter
from flatfinder.adapters.base import AdapterError

DATA=json.loads((Path(__file__).parent/'fixtures'/'sparkasse.json').read_text(encoding='utf-8'))

def test_real_offers_keep_actual_city_and_labeled_rent():
    listings=SparkasseAdapter.parse_items(DATA['firstPageEstates'])
    assert len(listings)==3
    assert listings[0].city=='Neu-Isenburg'
    assert listings[0].price_cold==1600
    assert listings[0].price_warm is None
    assert listings[0].sqm==175
    assert listings[0].lat==50.04222
    assert listings[0].position_approx

def test_syndicated_and_sale_listings_are_not_imported():
    item=copy.deepcopy(DATA['firstPageEstates'][0])
    item['eyeCatcher']=[{'label':'immowelt Kooperationsangebot'}]
    assert SparkasseAdapter.parse_items([item])==[]
    item=copy.deepcopy(DATA['firstPageEstates'][0]);item['marketingType']='buy'
    assert SparkasseAdapter.parse_items([item])==[]

def test_schema_change_fails_and_real_payload_is_readable():
    with pytest.raises(AdapterError):SparkasseAdapter.read_page('<html>blocked</html>')
    html='<script id="__NEXT_DATA__">'+json.dumps({'props':{'pageProps':DATA}})+'</script>'
    assert len(SparkasseAdapter.read_page(html)['firstPageEstates'])==3
