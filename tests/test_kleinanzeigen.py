from pathlib import Path
import pytest
import httpx
from flatfinder.adapters.kleinanzeigen import KleinanzeigenAdapter
from flatfinder.adapters.base import Blocked, AdapterError

FIX = Path(__file__).parent / "fixtures"

def test_real_cards_and_labeled_detail_price():
    items = KleinanzeigenAdapter.parse_page((FIX / "kleinanzeigen.html").read_text(encoding="utf-8"))
    assert len(items) == 3
    l = items[0]
    assert l.source_id == "3503362810"
    assert (l.zip, l.sqm, l.rooms) == ("65934", 43, 1)
    assert l.price_cold is None and l.price_warm is None
    KleinanzeigenAdapter.enrich(l, (FIX / "kleinanzeigen_detail.html").read_text(encoding="utf-8"))
    assert l.price_cold == 1060
    assert l.price_warm is None

def test_unknown_price_is_not_assumed_cold():
    l = KleinanzeigenAdapter.parse_page((FIX / "kleinanzeigen.html").read_text(encoding="utf-8"))[0]
    KleinanzeigenAdapter.enrich(l, '<h2>1.060 €</h2>')
    assert l.price_cold is None and l.price_warm is None

@pytest.mark.asyncio
async def test_block_and_changed_markup_fail_explicitly():
    for code, error in [(403, Blocked), (200, AdapterError)]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(code, text="challenge"))) as client:
            with pytest.raises(error):
                await KleinanzeigenAdapter(client).fetch()
