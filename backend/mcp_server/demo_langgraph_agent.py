"""Stretch B (#86): a LangGraph agent consuming the MCP server's tools.

langchain-mcp-adapters discovers the server's MCP tools and wraps each as a
LangChain tool, so a prebuilt ReAct agent can decide on its own to call
search_products. The point is consuming tools owned ELSEWHERE — the server
could be someone else's service; we only know its URL.

Needs the HTTP server running first:
  uv run python -m mcp_server.shopping_server --http   # terminal 1
  uv run python -m mcp_server.demo_langgraph_agent     # terminal 2
"""

import asyncio
from pathlib import Path

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

URL = "http://127.0.0.1:8765/mcp"


async def main():
    client = MultiServerMCPClient(
        {"wardrobe-shopping": {"transport": "streamable_http", "url": URL}}
    )
    tools = await client.get_tools()  # MCP tools → LangChain tools
    print("TOOLS ADAPTED:", [t.name for t in tools])

    # Haiku is plenty for tool routing, and cheap — this demo makes 2 calls
    # (pick the tool, then summarize its result).
    agent = create_agent(
        ChatAnthropic(model="claude-haiku-4-5-20251001", max_tokens=1024), tools
    )
    result = await agent.ainvoke(
        {
            "messages": [
                (
                    "user",
                    "Find me two options for a women's lightweight rain jacket "
                    "and summarize them in one line each with prices.",
                )
            ]
        }
    )
    print(result["messages"][-1].content)


if __name__ == "__main__":
    asyncio.run(main())
