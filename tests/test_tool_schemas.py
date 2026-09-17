"""
Durable regression test for the tool-schema/handler mismatch bug class found
during this session: a tool's handler can accept a parameter (even a
required one) that its tools/list schema entry never mentions, so no real
MCP client can ever discover or pass it. This class of bug was confirmed
live twice before being fixed: analyze_routine_structure's acd_path and
search_l5x_content's project_name were both accepted by their handlers but
missing from their advertised inputSchema.

This test constructs a real Studio5000MCPServer, calls the same
'tools/list' JSON-RPC path a real MCP client uses, and for every registered
tool checks two things against its actual handler signature
(inspect.signature, ignoring `self`):

  1. Every parameter the handler REQUIRES (no default) must appear in the
     schema's `properties` - otherwise no client can ever satisfy the call.
  2. Every property the schema ADVERTISES must correspond to an actual
     handler parameter - otherwise a client following the schema gets a
     TypeError at call time.

Tools whose handler takes no required parameters are allowed an empty
schema (e.g. get_sdk_statistics) - this test only fails on an actual
mismatch between what's promised and what the handler will accept.

Run with: python test_tool_schemas.py
"""
import inspect
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

os.environ.setdefault("STUDIO5000_DOC_PATHS",
    r"C:\Program Files (x86)\Rockwell Software\Studio 5000\Logix Designer\ENU\v35\Bin\Help\ENU\rs5000;"
    r"C:\Program Files (x86)\Rockwell Software\Studio 5000\Logix Designer\ENU\v36\Bin\Help\ENU\rs5000;"
    r"C:\Program Files (x86)\Rockwell Software\Studio 5000\Logix Designer\ENU\v37\Bin\Help\ENU\rs5000")

import asyncio
from mcp_server.studio5000_mcp_server import Studio5000MCPServer, handle_mcp_request

failures = []


def check(label, condition):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}")
    if not condition:
        failures.append(label)


async def main():
    paths = os.environ["STUDIO5000_DOC_PATHS"].split(";")
    doc_root = {"v35": paths[0], "v36": paths[1], "v37": paths[2]}
    server = Studio5000MCPServer(doc_root)

    response = await handle_mcp_request(server, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}
    })
    tools = response["result"]["tools"]
    print(f"=== {len(tools)} tools registered ===")
    check("at least one tool registered", len(tools) > 0)

    mismatch_count = 0
    for tool in tools:
        name = tool["name"]
        schema_props = set(tool["inputSchema"]["properties"].keys())
        handler = server.server.tools[name]["handler"]
        sig = inspect.signature(handler)

        handler_params = {p.name: p for p in sig.parameters.values() if p.name != "self"}
        required_params = {
            p.name for p in handler_params.values()
            if p.default is inspect.Parameter.empty
            and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
        }

        missing_from_schema = required_params - schema_props
        extra_in_schema = schema_props - set(handler_params.keys())

        if missing_from_schema:
            check(f"{name}: required handler param(s) {sorted(missing_from_schema)} "
                  f"missing from advertised schema", False)
            mismatch_count += 1
        if extra_in_schema:
            check(f"{name}: schema advertises {sorted(extra_in_schema)} "
                  f"which handler({name}) doesn't accept", False)
            mismatch_count += 1

    check(f"no tool has a schema/handler mismatch ({mismatch_count} found)", mismatch_count == 0)

    print("\n=== Spot-check: the two gaps this test is named for, now fixed ===")
    by_name = {t["name"]: t for t in tools}
    check("analyze_routine_structure's schema now advertises acd_path",
          "acd_path" in by_name["analyze_routine_structure"]["inputSchema"]["properties"])
    check("search_l5x_content's schema now advertises project_name",
          "project_name" in by_name["search_l5x_content"]["inputSchema"]["properties"])

    print("\n=== The two new xref tools are fully wired ===")
    for tool_name, required_param in (("find_tag_references", "tag_name"), ("search_tag_references", "pattern")):
        check(f"{tool_name} is registered", tool_name in by_name)
        if tool_name in by_name:
            check(f"{tool_name}'s schema requires {required_param}",
                  required_param in by_name[tool_name]["inputSchema"].get("required", []))

    print()
    if failures:
        print(f"=== {len(failures)} CHECK(S) FAILED ===")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("=== ALL CHECKS PASSED ===")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
