"""ForexFactory mirror: cache 30 min a pauza po 429 (dřív časté dotazy → rate limit celého kalendáře)."""
import httpx
import pytest
import respx

from app.sources import forex_factory as ff

XML = "<weeklyevents><event><title>X</title></event></weeklyevents>"


@pytest.fixture(autouse=True)
def reset_cache():
    ff._ff_cache.update(text=None, ts=0.0, blocked_until=0.0)
    yield
    ff._ff_cache.update(text=None, ts=0.0, blocked_until=0.0)


@pytest.mark.asyncio
@respx.mock
async def test_cached_within_window():
    route = respx.get(ff.FF_XML_URL).mock(return_value=httpx.Response(200, text=XML))
    assert await ff.fetch_ff_xml() == XML
    assert await ff.fetch_ff_xml() == XML
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_429_backs_off_and_serves_stale():
    ff._ff_cache.update(text=XML, ts=0.0)                      # stará kopie (expirovaná)
    route = respx.get(ff.FF_XML_URL).mock(return_value=httpx.Response(429, text="Rate Limited"))
    assert await ff.fetch_ff_xml() == XML                       # 429 → stará kopie
    assert ff._ff_cache["blocked_until"] > 0
    assert await ff.fetch_ff_xml() == XML                       # během pauzy se nedotazuje
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_429_without_cache_raises():
    respx.get(ff.FF_XML_URL).mock(return_value=httpx.Response(429, text="Rate Limited"))
    with pytest.raises(RuntimeError):
        await ff.fetch_ff_xml()
