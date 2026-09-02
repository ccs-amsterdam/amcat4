"""
MCP (Model Context Protocol) server for AmCAT4.

Exposes AmCAT4 query and annotation functionality as MCP tools at /mcp
(streamable HTTP transport), mounted on the main FastAPI app. Tools do not
call domain functions directly; they forward requests in-process to the
existing REST API (see client.py), so all authentication and role checks
apply unchanged.
"""
