"""Phase 3 demo: consume the wardrobe-shopping MCP server over stdio (#79)."""

import asyncio

from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BACKEND = str(Path(__file__).resolve().parents[1])  # backend path
params = StdioServerParameters(
    command="uv",
    args=[
        "run",
        "--directory",
        BACKEND,
        "python",
        "-m",
        "mcp_server.shopping_server",
    ],
)


async def main():
    async with stdio_client(params) as (read, write):
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
