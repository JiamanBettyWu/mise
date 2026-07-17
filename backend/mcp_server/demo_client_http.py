"""Consume the wardrobe-shopping MCP server over Streamable HTTP (#86).

Mirrors demo_client.py (stdio) so the transport diff is the whole lesson:
stdio spawns the server itself; here the server must ALREADY be running:

  uv run python -m mcp_server.shopping_server --http   # terminal 1
  uv run python -m mcp_server.demo_client_http         # terminal 2
"""

import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = "http://127.0.0.1:8765/mcp"


async def main():
    # No StdioServerParameters / no spawning — just a URL. Session layer
    # (initialize / list_tools / call_tool) is identical to the stdio demo.
    async with streamablehttp_client(URL) as (read, write, _get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("TOOLS DISCOVERED:", [t.name for t in tools.tools])

            result = await session.call_tool(
                "search_products", {"query": "women's handbag", "num": 2}
            )
    for p in result.structuredContent["result"]:
        print(f"  {p['title']} — {p['price']} ({p['retailer']})")

    return result


if __name__ == "__main__":
    asyncio.run(main())
