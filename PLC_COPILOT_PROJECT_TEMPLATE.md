# Setting Up a "PLC Copilot" Project

This describes the project convention we use on top of this MCP server to turn Claude Code into
a per-client Studio 5000 copilot — one that explains ladder logic, traces faults, cross-references
tags, and generates/inserts new logic with every answer tied to a specific rung, routine, or tag,
instead of relying on general Logix knowledge alone. It's a folder/documentation pattern, not new
code — anyone on the team can stand this up for their own client project once this server is
installed (see [README.md](README.md) / [ONBOARDING_CHECKLIST.md](ONBOARDING_CHECKLIST.md)).

## Why this pattern

The MCP server gives Claude tools to index and search ACD/L5X/PDF/tag data
(`index_acd_project`, `index_exported_l5x_files`, `index_pdf_drawings`, `index_tag_csv`,
`search_tags`, `search_l5x_content`, `search_drawings`, `find_related_tags`, etc.) plus tools to
generate and validate logic (`generate_ladder_logic`, `smart_insert_logic`, `create_l5x_routine`,
`validate_ladder_logic`). Those tools work on whatever files you point them at — but Claude still
needs to know **which folder holds what**, **which files are safe to write to**, and **which prior
jobs' logic is worth reusing** for the client you're working on right now. A `CLAUDE.md` at the
project root plus a companion index file is how you tell it that once, so every session afterward
starts from the same map instead of re-discovering the project layout from scratch.

## Folder layout

Create one project folder per client job, laid out like this:

```
<ProjectName>/
  <ProjectName>.ACD          # the live project, edited directly in Studio 5000
  Assets/                    # read-only reference ACDs from prior jobs (other closed-source
                              # integrator projects you're allowed to mine for reusable logic)
  01 AOIs/                   # L5X exports of reusable AOIs pulled from Assets/
  02 Routines/               # L5X exports of reusable routines pulled from Assets/
  03 UDTs/                   # L5X exports of reusable UDTs pulled from Assets/
  Documentation/             # vendor/product reference PDFs (manuals, assembly drawings)
  Drawings/                  # site electrical/mechanical drawing sets
  Logix_Index.md             # indexes 01/02/03 above + system context (see below)
  CLAUDE.md                  # project instructions (see template below)
```

`01 AOIs/`, `02 Routines/`, and `03 UDTs/` don't have to be filled in up front — populate them as
you find reusable blocks worth pulling out of `Assets/` for the current job. Keep `Assets/*.ACD`
untouched; open and close them in Studio 5000 without saving, and only export the pieces you want
as standalone L5X into the numbered folders above.

## `Logix_Index.md`

This is the "what's in the reuse library and why" file. For each AOI/Routine/UDT pulled into
`01/02/03`, record: the source project it came from, and *why* it's relevant to the current job
(what it does, what it's a candidate replacement/analog for). Add a system-context section
summarizing the client's own scope document (DOO, spec, whatever they call it) and a "Suggested
usage" section mapping subsystems of the new job to specific reference files. Flag anywhere the
source project's hardware/fieldbus differs from the current job's (e.g. Profibus vs. Ethernet/IP)
so a suggested reuse isn't mistaken for a drop-in port.

## `CLAUDE.md` template

Copy this into the new project's root and fill in the bracketed parts:

```markdown
# PLC Copilot (<ProjectName>)

Act as a Studio 5000 logic-development and troubleshooting copilot for this <one-line project
description — controller model, HMI platform, what the system does> — explain ladder logic, trace
faults, cross-reference tags, and generate/insert new logic, with every answer tied to a specific
rung, routine, or tag rather than general Logix knowledge alone.

## Project layout
- `<ProjectName>.ACD` — the live project, edited directly in Studio 5000.
- `Assets/` — read-only reference ACDs from prior integrator jobs (<list them>). Never modify
  these; they're closed source files kept only for indexing/search.
- `01 AOIs/`, `02 Routines/`, `03 UDTs/` — L5X exports pulled from `Assets/` as reusable reference
  material for building <ProjectName>.
- `Documentation/` — vendor/product reference PDFs. Read-only reference material, not project
  deliverables.
- `Drawings/` — site electrical/mechanical drawing sets. Read-only reference material for tracing
  field I/O and equipment layout.
- `Logix_Index.md` — indexes what's in `01 AOIs/`, `02 Routines/`, `03 UDTs/` and why, plus system
  context. Read this first for "what should I reuse for X" questions before searching the raw L5X
  files.

## Live-file safety rule
`<ProjectName>.ACD` is very likely open in Studio 5000 during a session. Studio 5000 locks `.ACD`
files exclusively, so:
- Never attempt to write to `<ProjectName>.ACD` directly (e.g. `create_acd_project` targeting it)
  while it may be open — this will conflict with the open session or risk corruption.
- To analyze current live logic, ask for a fresh `.L5X` export of the routine/program in question
  (Studio 5000: right-click the routine/program → Export) rather than reading the ACD directly.
- To add new logic, generate/insert against an `.L5X` file, then hand it back for review — the
  change only lands once it's manually imported via Studio 5000's Import Routine/Rungs. Never
  assume a generated change is "in" the project until that import happens.
- The `Assets/*.ACD` files are closed reference sources — indexing/searching those directly is
  safe and doesn't hit the same lock.

## Working style
- Cite the specific rung, routine, tag, or L5X file backing every explanation.
- When asked to reuse a block from the AOI/Routine/UDT library, check `Logix_Index.md`'s
  "Suggested usage" section first, and flag when the source hardware/fieldbus differs before
  recommending a straight port.
```

## Bringing it online

1. Create the folder layout above under a new project directory (outside this repo — one
   `CLAUDE.md`-rooted folder per client job).
2. Populate `Assets/` with the prior-job ACDs relevant to this client's hardware/process.
3. Open Claude Code in that project folder (the server's MCP config from `setup.py` is global, so
   any project folder can use it).
4. Ask Claude to index the project: point `index_acd_project` at `Assets/*.ACD` and (once you have
   one) the current project's `.ACD`, `index_pdf_drawings` at `Documentation/`/`Drawings/`, and
   `index_tag_csv` if you export a tag list.
5. Have Claude pull candidate AOIs/Routines/UDTs into `01/02/03` and draft `Logix_Index.md` as it
   goes (use `search_l5x_content`/`find_related_components` to survey `Assets/` first).
6. Fill in `CLAUDE.md` from the template above once you know the project's real name, hardware,
   and source-job list.
7. From then on, treat the live-file safety rule as non-negotiable: all logic changes go through
   an L5X export → Claude edits/generates → manual Studio 5000 import round-trip.

This is the same model behind our own `THD_LG_CP2` GTPS project — that project's `CLAUDE.md` and
`Logix_Index.md` aren't in this repo (client-confidential), but they follow exactly this pattern.
