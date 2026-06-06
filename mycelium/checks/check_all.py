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

"""Run every connection / runtime check sequentially.

Layout:
  mongo/    - MongoDB connectivity
  gitlab/   - GitLab read + write operations
  vertex/   - Vertex AI + ADK runtime
  mcp/      - MCP servers (Mycelium, GitLab MCP, MongoDB MCP)
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
