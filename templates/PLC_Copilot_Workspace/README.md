# PLC Copilot workspace template

Copy this whole folder to start a new per-client project, rename it to the job (for example
`ACME_LineA/`), and open Claude Code in it. The layout mirrors the workspace we use on THD_LG_CP2.
Folders start empty (`.gitkeep` only); fill them as the job needs them. Delete `.gitkeep` files in
your copy if you like.

```
<ProjectName>/
  <ProjectName>.ACD      live project, edited in Studio 5000 (never written by Claude)
  CLAUDE.md              copy of CLAUDE.template.md, filled in
  Logix_Index.md         optional: what is in 01-03 and why (see PLC_COPILOT_PROJECT_TEMPLATE.md)
  01 AOIs/               reusable AOIs as L5X, pulled from Assets/ or the shared library
  02 Routines/           reusable routines as L5X
  03 UDTs/               reusable UDTs as L5X
  04 Controller Tags/    tag CSV exports of the live project (feed index_tag_csv)
  05 Programs/           fresh L5X exports of the live project's programs and routines
  06 Emulate3D/          only if the job uses Emulate3D: model, PLC programs, scripts, tests
  07 Compare/            version comparisons and patch L5Xs (for example V35 vs V37)
  Assets/                read-only reference ACDs from prior jobs; never modified
  Documentation/         project documents and manuals (or a pointer to the shared library)
  Drawings/              facility and electrical drawings (or a pointer to the shared library)
  Planning/              design notes, scratch work, anything not yet part of the project
  _Archive/              retired files kept only for rollback
```

## Rules the layout relies on

- The live `.ACD` is usually open in Studio 5000 and locked. Claude reads fresh L5X exports from
  `05 Programs/`, never the ACD itself.
- Generated logic is written as L5X and only becomes part of the project when you import it in
  Studio 5000.
- `Assets/` is closed-source reference material: index and search it, never edit it.
- Folders created by the MCP server's indexing (`l5x_vector_cache/`, `sdk_vector_cache/`,
  `instruction_vector_cache_*`) are generated; add them to your own `.gitignore` if the project is
  under version control.
- Large shared material (manuals, standard AOI libraries, drawing sets) belongs in the team's shared
  library, not copied into each project. Use `Documentation/` and `Drawings/` for what is specific
  to this job.
