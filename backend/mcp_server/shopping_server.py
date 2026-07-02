"""MCP server exposing wardrobe product search over stdio (#79 learning track).

Thin adapter over services.search — no business logic lives here.
Run from backend/:  uv run python -m mcp_server.shopping_server
"""

from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import Field

from schemas import PurchaseResult
from services.search import search_products as _search  # alias avoids name clash

mcp = FastMCP("wardrobe-shopping")  # ← (1) the server name a client sees

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
    mcp.run()  # stdio transport by default
