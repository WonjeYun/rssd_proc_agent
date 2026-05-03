"""
FFIEC MCP database tools were removed on purpose.

The interactive agent is expected to run **Python scripts via Bash** that import
`ffiec_rssd_agent.db` (or use `sqlite3` against the same SQLite file) so bulk
work stays in one process without MCP round-trips or row limits.

`SERVER_NAME` / `ALLOWED_TOOL_NAMES` remain for any future optional MCP wiring;
both are unused while `agent.py` registers no FFIEC MCP server.

The previous MCP tool implementations live in **`legacy_tools`** (`create_ffiec_server`,
`ALL_TOOLS`) for example runs or custom wiring.
"""

SERVER_NAME = "ffiec"
SERVER_VERSION = "1.0.0"

ALLOWED_TOOL_NAMES: list[str] = []
