# Project MCP tools

This directory contains the MCP-capable tools selected from the kit's `# MCP 工具.txt`.

## Installed servers

- `ponytail`: official Ponytail MCP server, backed by the checkout in `ponytail/`.
- `symdex`: official SymDex 0.1.26, installed in the Python 3.11 virtualenv
  `symdex-venv311/`.

The client configuration is in `mcp.json`. It uses absolute paths for this
machine and can be merged into an MCP host's `mcpServers` configuration.

SymDex is installed without optional embedding backends. Its structural,
text-search, route, graph, and MCP features are available; semantic search
requires an additional optional backend and indexing step.

## Other entries in the source list

RTK, OpenSpec, and Archify are CLI/agent tools rather than MCP servers, so they
are not represented as MCP entries here. LLM Wiki is an external desktop app,
and WikiSkill is a paper/reference; neither is an MCP installation target.
