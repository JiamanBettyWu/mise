"""SerpAPI Google purchase"""

import logging
import os
import time

import httpx

from schemas import PurchaseResult

logger = logging.getLogger(__name__)
# #88: the SerpAPI key rides in the request URL's query string, and httpx logs
# full URLs at INFO — silence its request logger so the key never hits the logs.
logging.getLogger("httpx").setLevel(logging.WARNING)

SERPAPI_URL = "https://serpapi.com/search"
CACHE_TTL = 30 * 60
_PURCHASE_CACHE: dict[str, tuple[float, list]] = {}


def _fetch_search_results(query: str) -> list[dict]:
    now = time.time()

    cached = _PURCHASE_CACHE.get(query)
    if cached and now - cached[0] < CACHE_TTL:
        return cached[1]

    api_key = os.environ.get("SERPAPI_API_KEY")
    if api_key is None:
        logger.warning("SerpAPI key is None.")
        return []

    try:
        resp = httpx.get(
            SERPAPI_URL,
            params={"engine": "google_shopping", "api_key": api_key, "q": query},
            # #107: shaped timeout — fail fast when SerpAPI is unreachable, but
            # wait out live google_shopping searches, which routinely take 20-30s
            # server-side. A shorter read timeout abandons a search that still
            # completes, bills, and caches on SerpAPI's end.
            timeout=httpx.Timeout(35, connect=5),
        )

        resp.raise_for_status()
        data = resp.json().get("shopping_results", [])
    except httpx.HTTPError as e:
        # Don't log `e` itself — HTTPStatusError's message embeds the full
        # request URL, api_key query param included (#88's sibling leak).
        status = getattr(getattr(e, "response", None), "status_code", None)
        logger.error(
            "SerpAPI search failed for %r: %s (status=%s)",
            query,
            type(e).__name__,
            status,
        )
        return []

    # caching all results
    _PURCHASE_CACHE[query] = (now, data)
    return data


def search_products(query: str, num: int = 4) -> list[PurchaseResult]:

    data = _fetch_search_results(query)

    if len(data) == 0:
        return []

    data_truc = data[:num]  # truncate the results

    return [
        PurchaseResult(
            title=r["title"],
            url=r["product_link"],
            image_url=r.get("thumbnail"),
            price=r.get("price"),
            retailer=r.get("source"),
        )
        for r in data_truc
        if r.get("title") is not None and r.get("product_link") is not None
    ]
