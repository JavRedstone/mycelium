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

"""Mycelium ADK agent layer.

Each submodule (`act_agent`, `analyst_agent`, `planner_agent`) exposes its own
`root_agent` (an ADK `Agent`) plus a thin async entry point used by the pipeline.

The package root deliberately does NOT eager-import any agent, because
`act_agent.build_root_agent()` opens MCP toolsets (GitLab over HTTP and MongoDB
over a stdio subprocess) at construction time. Import the specific submodule
you need.
"""
