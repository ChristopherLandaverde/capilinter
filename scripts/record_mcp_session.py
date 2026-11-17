"""Record a real MCP session against `capilinter-mcp` for docs/transcripts/13-mcp-session.txt.

Starts the server over stdio with the MCP SDK's client (the server found on PATH),
lists the tools, then calls three of them. Deterministic: the payload is passed
as payload_json, so no machine-specific path appears in the output.
"""

import json
import os
import shutil
import sys
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent


async def main() -> None:
    server = shutil.which("capilinter-mcp")
    if server is None:
        sys.exit("capilinter-mcp is not on PATH; install with: pip install '.[mcp]'")
    params = StdioServerParameters(command=server, args=[], env=dict(os.environ))
    payload = (ROOT / "fixtures" / "unhashed_pii.json").read_text(encoding="utf-8")
    calls = [
        ("audit_payload", {"payload_json": payload}),
        ("hash_value", {"field": "em", "value": "Jane.Doe@Example.com"}),
        ("explain_check", {"code": "RAW_PII_UNHASHED_EMAIL"}),
    ]
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        init = await session.initialize()
        print(f"server: {init.server_info.name} {init.server_info.version}")
        tools = await session.list_tools()
        print("tools/list:")
        for tool in tools.tools:
            ro = bool(tool.annotations and tool.annotations.read_only_hint)
            print(f"  {tool.name}  read_only={ro}")
        for name, args in calls:
            shown = {k: ("<fixtures/unhashed_pii.json>" if k == "payload_json" else v) for k, v in args.items()}
            print(f"\ntools/call {name} {json.dumps(shown)}")
            result = await session.call_tool(name, args)
            body = json.loads(result.content[0].text)
            if name == "audit_payload":
                event = body["events"][0]
                body = {
                    "schema_version": body["schema_version"],
                    "passed": body["passed"],
                    "codes": [i["code"] for i in event["issues"]],
                    "emq_estimate": event["emq_estimate"]["score"],
                }
                print("(trimmed to schema_version, passed, issue codes and estimate)")
            print(f"is_error={result.is_error}")
            print(json.dumps(body, indent=2))


if __name__ == "__main__":
    anyio.run(main)
