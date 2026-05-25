from dotenv import load_dotenv
import asyncio
import os
import sys

load_dotenv()

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

_NPX = "npx.cmd" if sys.platform == "win32" else "npx"


async def main():
    env = dict(os.environ)
    env["MDB_MCP_CONNECTION_STRING"] = os.environ["MONGODB_URI"]

    params = StdioServerParameters(
        command=_NPX,
        args=["-y", "@mongodb-js/mongodb-mcp-server"],
        env=env,
    )

    try:
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as session:
                await session.initialize()
                result = await session.list_tools()
                print(f"[OK] MongoDB MCP - {len(result.tools)} tools available")
                for t in result.tools:
                    desc = (t.description or "").splitlines()[0][:80]
                    print(f"     * {t.name}: {desc}")
    except Exception as e:
        print(f"[FAIL] MongoDB MCP - {e}")


if __name__ == "__main__":
    asyncio.run(main())
