"""Unit tests for the SerpAPI product-search wrapper (#10).

All offline. The mapping/truncation/skip tests patch `_fetch_search_results`
so no network is touched; the resilience tests assert the two paths that must
NOT crash the trip plan — a missing API key and an HTTP failure — each return
[] instead of raising.
"""

import httpx
import pytest

from schemas import PurchaseResult
from services import search
from services.search import search_products

# Six well-formed SerpAPI shopping_results, using the real field names
# (product_link / thumbnail / source) the wrapper reads.
FAKE_RESULTS = [
    {
        "title": f"Item {i}",
        "product_link": f"https://shop.example/{i}",
        "thumbnail": f"https://img.example/{i}.jpg",
        "price": f"${i}.00",
        "source": "ShopCo",
    }
    for i in range(6)
]


@pytest.fixture(autouse=True)
def _clear_cache():
    # _PURCHASE_CACHE is module-global and persists across tests; clear it so
    # one test's results can't leak into another via a shared query key.
    search._PURCHASE_CACHE.clear()
    yield
    search._PURCHASE_CACHE.clear()


def test_maps_and_truncates(monkeypatch):
    monkeypatch.setattr(search, "_fetch_search_results", lambda query: FAKE_RESULTS)

    out = search_products("rain jacket", num=4)

    assert len(out) == 4  # truncated from the 6 returned
    first = out[0]
    assert isinstance(first, PurchaseResult)
    assert first.title == "Item 0"
    assert first.url == "https://shop.example/0"       # product_link -> url
    assert first.image_url == "https://img.example/0.jpg"
    assert first.price == "$0.00"
    assert first.retailer == "ShopCo"                  # source -> retailer


def test_skips_malformed_results(monkeypatch):
    results = [
        {"product_link": "https://shop.example/x", "source": "S"},  # no title
        {"title": "No link"},                                       # no product_link
        {"title": "Good", "product_link": "https://shop.example/g"},
    ]
    monkeypatch.setattr(search, "_fetch_search_results", lambda query: results)

    out = search_products("rain jacket")

    assert len(out) == 1  # the two missing a required field are dropped, not raised
    assert out[0].title == "Good"


def test_missing_key_returns_empty(monkeypatch):
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)

    def _no_network(*args, **kwargs):
        raise AssertionError("httpx.get must not be called without an API key")

    monkeypatch.setattr(search.httpx, "get", _no_network)

    assert search_products("rain jacket") == []


def test_http_error_returns_empty(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "dummy")

    def _boom(*args, **kwargs):
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(search.httpx, "get", _boom)

    assert search_products("rain jacket") == []
