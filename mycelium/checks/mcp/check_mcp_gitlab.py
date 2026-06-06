# Copyright 2026 Javier Huang
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
GitLab MCP connectivity check.

GitLab MCP uses OAuth 2.0 - not PAT Bearer tokens in the connection headers.
mcp-remote handles the OAuth handshake and caches the token in ~/.mcp-auth/
so subsequent runs (including the autonomous agent loop) work without a browser.

FIRST RUN: a browser window will open for you to authorise the OAuth request.
SUBSEQUENT RUNS: cached token is reused automatically - no browser required.

Prerequisites:
  - GitLab Duo enabled on your account (Premium/Ultimate tier)
  - Beta and experimental features turned on (GitLab > Edit profile > Preferences)
  - Node.js 20+ with `npx` in PATH
  - Complete first-run OAuth once: npx -y mcp-remote@latest https://gitlab.com/api/v4/mcp

Reference: https://docs.gitlab.com/ee/user/gitlab_duo/mcp/
"""
import asyncio
import os
import sys
import warnings

# Suppress asyncio subprocess pipe cleanup warnings on Windows.
warnings.filterwarnings("ignore", category=ResourceWarning)

from dotenv import load_dotenv

load_dotenv()

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

_NPX = "npx.cmd" if sys.platform == "win32" else "npx"
_TIMEOUT = 120.0


async def main() -> int:
    gitlab_url = os.getenv("GITLAB_URL", "https://gitlab.com")
    mcp_url = f"{gitlab_url}/api/v4/mcp"

    print(f"     GitLab MCP endpoint: {mcp_url}")
    print("     Transport: stdio via mcp-remote (OAuth 2.0)")

    server_params = StdioServerParameters(
        command=_NPX,
        args=["-y", "mcp-remote@latest", mcp_url],
        env=dict(os.environ),
    )

    try:
        async with stdio_client(server_params) as (r, w):
            async with ClientSession(r, w) as session:
                await asyncio.wait_for(session.initialize(), timeout=_TIMEOUT)
                result = await asyncio.wait_for(session.list_tools(), timeout=_TIMEOUT)
                print(f"[OK] GitLab MCP - {len(result.tools)} tools available")
                for t in result.tools:
                    desc = (t.description or "").splitlines()[0][:80]
                    print(f"     * {t.name}: {desc}")
        return 0

    except ExceptionGroup as eg:
        # Unwrap to find the root cause.
        def _root(exc: BaseException) -> str:
            if isinstance(exc, BaseExceptionGroup):
                return _root(exc.exceptions[0]) if exc.exceptions else str(exc)
            cause = exc.__cause__ or exc.__context__
            return f"{type(exc).__name__}: {exc}" + (f" (caused by {_root(cause)})" if cause else "")
        print(f"[FAIL] GitLab MCP - {_root(eg)}")

    except asyncio.TimeoutError:
        print(f"[FAIL] GitLab MCP - timed out after {_TIMEOUT}s")
        print("       If this is the first run, re-run standalone to complete OAuth:")
        print(f"         python checks/check_mcp_gitlab.py")

    except FileNotFoundError:
        print("[FAIL] GitLab MCP - `npx` not found. Install Node.js 20+ and add it to PATH.")
        return 1

    except Exception as exc:
        print(f"[FAIL] GitLab MCP - {type(exc).__name__}: {exc}")

    print()
    print("  Troubleshooting:")
    print("  1. Complete OAuth first run:  npx -y mcp-remote@latest " + mcp_url)
    print("  2. Enable beta features: GitLab.com > Edit profile > Preferences")
    print("  3. Clear stale OAuth cache:")
    print("     del /s /q %USERPROFILE%\\.mcp-auth\\mcp-remote*  (Windows)")
    print("     rm -rf ~/.mcp-auth/mcp-remote*                   (Linux/macOS)")
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
