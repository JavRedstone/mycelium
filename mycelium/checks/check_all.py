"""Run every connection / runtime check sequentially.

Layout:
  mongo/    — MongoDB connectivity
  gitlab/   — GitLab read + write operations
  vertex/   — Vertex AI + ADK runtime
  mcp/      — MCP servers (Mycelium, GitLab MCP, MongoDB MCP)
"""
import subprocess
import sys
from pathlib import Path

CHECKS = [
    "mongo/check_mongo.py",
    "gitlab/check_gitlab.py",
    "gitlab/check_write.py",
    "vertex/check_vertex.py",
    "vertex/check_adk.py",
    "mcp/check_mcp_mycelium.py",
    "mcp/check_mcp_gitlab.py",
    "mcp/check_mcp_mongo.py",
]
checks_dir = Path(__file__).parent

for check in CHECKS:
    subprocess.run([sys.executable, str(checks_dir / check)])
