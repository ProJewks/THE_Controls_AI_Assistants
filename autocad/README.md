# AutoCAD MCP

MCP server that drives a running AutoCAD instance through COM automation (`pywin32`), so an AI assistant can open, draw in, and save drawings.

**Windows only. AutoCAD must be installed and running.**

## Tools
Drawing lifecycle (`new_drawing`, `open_drawing`, `save_drawing`, `save_drawing_as`, `close_drawing`, `list_open_drawings`), geometry (`draw_line`, `draw_polyline`, `draw_rectangle`, `draw_circle`, `draw_arc`, `add_text`, `add_mtext`), layers and blocks (`create_layer`, `set_current_layer`, `list_layers`, `insert_block`, `list_blocks`), entity management (`list_entities`, `get_entity`, `move_entity`, `delete_entity`), view (`zoom_extents`), and escape hatches (`run_command`, `run_autolisp`), plus `autocad_status`.

## Install
```powershell
cd autocad
python -m venv .venv
.venv\Scripts\pip install -e .
```

## Register with Claude Code
```json
{
  "mcpServers": {
    "autocad": {
      "type": "stdio",
      "command": "C:\path\to\autocad\.venv\Scripts\python.exe",
      "args": ["-m", "autocad_mcp.server"]
    }
  }
}
```
