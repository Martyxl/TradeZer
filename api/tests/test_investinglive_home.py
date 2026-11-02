"""investingLive homepage → titulky vydání dřív než RSS (zkrácený reálný HTML z 2. 11. 2026)."""
import hashlib
from datetime import datetime

import pytest

from app.sources.base import RawNewsItem
from app.sources.rss_adapter import InvestingLiveAdapter, build_default_rss_adapters

SLOT = ('<a class="x" href="/news/{slug}/" target="_self"><h3 class="ArticleSlotHeader-module-scss-module__otcTeq__'
        'articleSlotHeader__title">{title}</h3></a><div><div class="activator__hover-content">'
        '<time dateTime="{ts}" class="A">x</time></div></div>')
PAGE = "".join([
    SLOT.format(slug="us-ism-manufacturing-pmi-for-october-55-5-versus-54-5-estimate",
                title="US ISM manufacturing PMI for October 55.5 versus 54.5 estimate", ts="2026-11-02T15:00:17.2502175Z"),
    SLOT.format(slug="us-s-p-global-final-manufacturing-pmi", title="US S&amp;P Global final manufacturing PMI",
                ts="2026-11-02T14:45:11Z"),
    '<a href="/news/no-time/"><h3 class="articleSlotHeader__title">Bez času</h3></a>',
])
ISM_URL = "https://investinglive.com/news/us-ism-manufacturing-pmi-for-october-55-5-versus-54-5-estimate/"


def test_parse_home():
    rows = InvestingLiveAdapter.parse_home(PAGE)
    assert [r["title"] for r in rows] == ["US ISM manufacturing PMI for October 55.5 versus 54.5 estimate",
                                          "US S&P Global final manufacturing PMI"]
    assert rows[0]["url"] == ISM_URL
    assert rows[0]["published_at"] == datetime(2026, 11, 2, 15, 0, 17, 250217)


@pytest.mark.asyncio
async def test_fetch_adds_only_newer_than_rss_with_rss_compatible_id(monkeypatch):
    a = next(x for x in build_default_rss_adapters() if x.name == "rss_investinglive")
    assert isinstance(a, InvestingLiveAdapter)
    sp = "https://investinglive.com/news/us-s-p-global-final-manufacturing-pmi/"
    rss = [RawNewsItem(source=a.name, external_id=hashlib.sha256(sp.encode()).hexdigest()[:32], title="S&P",
                       body=None, url=sp, published_at=datetime(2026, 11, 2, 14, 45, 11), raw_payload={},
                       instruments_hint=[])]

    async def fake_rss(self):
        return list(rss)

    async def fake_home(self):
        return PAGE

    monkeypatch.setattr("app.sources.rss_adapter.RSSAdapter.fetch", fake_rss)
    monkeypatch.setattr(InvestingLiveAdapter, "_fetch_home", fake_home)
    items = await a.fetch()
    assert [i.url for i in items] == [ISM_URL, sp]
    assert items[0].external_id == hashlib.sha256(ISM_URL.encode()).hexdigest()[:32]
