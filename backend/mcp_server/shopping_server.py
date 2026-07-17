"""MCP server exposing wardrobe product search (#79 stdio, #86 Streamable HTTP).

Thin adapter over services.search — no business logic lives here.
Run from backend/:
  uv run python -m mcp_server.shopping_server          # stdio (spawned per client)
  uv run python -m mcp_server.shopping_server --http   # standalone HTTP on :8765/mcp
"""

import sys
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import Field

from schemas import PurchaseResult
from services.search import search_products as _search  # alias avoids name clash

mcp = FastMCP("wardrobe-shopping", port=8765)  # ← (1) the server name a client sees

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


@mcp.tool()
def search_products(
    query: Annotated[
        str,
        Field(
            description="Shopping search terms, e.g. 'women's lightweight rain jacket' "
        ),
    ],
    num: Annotated[
        int, Field(default=4, description="Max results to return (1-10).")
    ] = 4,
) -> list[PurchaseResult]:
    """
    Search Google Shopping for a wardrobe item using query as the search term.

    Use this tool when the user asks for shopping recommendations for a wardrobe item.

    When the search is successful, this tool returns a list of products with title/url/price/retailer; empty list if nothing found.

    This tool never raises. It can return an empty list [] for any numbers of reasons, including API key error, an HTTP
    failure, or a "no products found."

    """
    return _search(query, num)


if __name__ == "__main__":
    if "--http" in sys.argv:
        # Standalone service at http://127.0.0.1:8765/mcp — many clients can
        # connect to ONE long-lived process (vs stdio: one spawned process per
        # client). Trade-off: you now own a port, a lifecycle, and auth.
        mcp.run(transport="streamable-http")
    else:
        mcp.run()  # stdio: client spawns us and owns our lifetime
