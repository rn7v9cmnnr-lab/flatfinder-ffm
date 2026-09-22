from pathlib import Path
import pytest
import httpx
from flatfinder.adapters.ohnemakler import OhneMaklerAdapter
from flatfinder.adapters.base import AdapterError

FIX = Path(__file__).parent / "fixtures"

def test_real_cards_only_frankfurt_and_explicit_cold_price():
    html = (FIX / "ohnemakler.html").read_text(encoding="utf-8")
    items = OhneMaklerAdapter.parse_page(html)
    assert len(items) == 24
    l = items[0]
    assert (l.source_id, l.zip, l.sqm, l.rooms) == ("142569", "60438", 35, 1.5)
    assert l.price_cold is None
    OhneMaklerAdapter.enrich(l, (FIX / "ohnemakler_detail.html").read_text(encoding="utf-8"))
    assert l.price_cold == 880
    assert l.price_warm is None
    assert not OhneMaklerAdapter.parse_page(html.replace("Frankfurt", "Offenbach"))

@pytest.mark.asyncio
async def test_changed_markup_does_not_report_success():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text="maintenance"))) as client:
        with pytest.raises(AdapterError):
            await OhneMaklerAdapter(client).fetch()
