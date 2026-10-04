# Emulate3D MCP

Emulate3D does not need code from this repo. The MCP server is built into the Emulate3D application and is served over HTTP, so this folder only documents how to connect to it.

## Connect
1. Start Emulate3D and enable its MCP server (default `http://localhost:9080/mcp`).
2. Register it with Claude Code:
```json
{
  "mcpServers": {
    "emulate3d": {
      "type": "http",
      "url": "http://localhost:9080/mcp"
    }
  }
}
```
Or from the CLI: `claude mcp add --transport http emulate3d http://localhost:9080/mcp`

## Notes
- Call `get_capabilities` first. It reports which permissions the session has (scene read/modify, script read/modify, test runs, catalog, connections) and which skills are available.
- Skills exposed by the app: `csharp-scripting`, `custom-mcp-tools`, `model-building`, `test-framework`. Load them with `get_skill`.
- Format all numbers with the invariant culture (`.` decimal separator, no digit grouping), including Vector3 values such as `(1.5, 2.25, 3.75)`.
- Tools cover scene editing (visuals, catalog items, conveyor paths), C# scripting, tag/server connections (OPC and similar), and scripted tests.
