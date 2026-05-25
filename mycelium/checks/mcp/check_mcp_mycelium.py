"""
Mycelium custom MCP server connectivity check.

Starts the custom MCP server (connectors/mcp_server.py) as a stdio subprocess and
verifies that all expected tools are registered.

Prerequisites:
  - MongoDB running and reachable (MONGODB_URI in .env)
  - GITLAB_TOKEN and GITLAB_PROJECT_ID set in .env
"""
import asyncio
import sys
import warnings
from pathlib import Path

# Suppress asyncio subprocess pipe cleanup warnings on Windows.
warnings.filterwarnings("ignore", category=ResourceWarning)

# Make project root importable.
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv

load_dotenv()

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

_SERVER_PY = _ROOT / "connectors" / "mcp_server.py"
_TIMEOUT = 30.0

_EXPECTED_TOOLS = {
    "get_concerns",
    "get_module_experts",
    "get_orphaned_modules",
    "suggest_assignee",
    "get_gitlab_project_state",
    "create_issue",
    "add_comment",
    "assign_issue",
    "generate_onboarding_pack",
    "generate_offboarding_artifact",
}


async def main() -> int:
    print(f"     Server: {_SERVER_PY}")
    print(f"     Python: {sys.executable}")

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(_SERVER_PY)],
        env=None,
    )

    try:
        async with stdio_client(server_params) as (r, w):
            async with ClientSession(r, w) as session:
                await asyncio.wait_for(session.initialize(), timeout=_TIMEOUT)
                result = await asyncio.wait_for(session.list_tools(), timeout=_TIMEOUT)
                tool_names = {t.name for t in result.tools}
                print(f"[OK] Mycelium MCP - {len(result.tools)} tools registered")
                for t in result.tools:
                    desc = (t.description or "").splitlines()[0][:80]
                    status = "[OK]" if t.name in _EXPECTED_TOOLS else "[EXTRA]"
                    print(f"     {status} {t.name}: {desc}")

                missing = _EXPECTED_TOOLS - tool_names
                if missing:
                    print(f"[WARN] Missing expected tools: {', '.join(sorted(missing))}")
                    return 1
        return 0

    except asyncio.TimeoutError:
        print(f"[FAIL] Mycelium MCP - timed out after {_TIMEOUT}s")
        return 1

    except FileNotFoundError as exc:
        print(f"[FAIL] Mycelium MCP - {exc}")
        return 1

    except Exception as exc:
        print(f"[FAIL] Mycelium MCP - {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
