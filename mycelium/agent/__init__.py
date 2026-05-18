"""Mycelium ADK agent layer.

Each submodule (`act_agent`, `analyst_agent`, `planner_agent`) exposes its own
`root_agent` (an ADK `Agent`) plus a thin async entry point used by the pipeline.

The package root deliberately does NOT eager-import any agent, because
`act_agent.build_root_agent()` opens MCP toolsets (GitLab over HTTP and MongoDB
over a stdio subprocess) at construction time. Import the specific submodule
you need.
"""
