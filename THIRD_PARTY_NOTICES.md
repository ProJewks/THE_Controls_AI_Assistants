# Third-Party Notices

This project is not itself under a published license (see the note in
`README.md`'s "License and Legal" section). This file exists to satisfy the
attribution requirement of third-party code whose *approach* was adapted
into this project, even though no code was copied verbatim.

## nodeblue-ai/studio5000-mcp-server

**Source**: https://github.com/nodeblue-ai/studio5000-mcp-server
**License**: MIT License
**Copyright**: Copyright (c) 2026 Nodeblue

```
MIT License

Copyright (c) 2026 Nodeblue

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### What was adapted, and what wasn't

`src/l5x_analyzer/l5x_xref.py` (backing the `find_tag_references` and
`search_tag_references` MCP tools) adapts nodeblue's general *approach* to
building an exact-match tag cross-reference from parsed Logix logic - the
idea of tokenizing NeutralText/Structured Text and classifying each token as
either an instruction/AOI call or a tag reference. No source code was copied
from nodeblue's repository; the implementation here is written independently
and differs in several deliberate ways (each explained in full in the module
docstring of `l5x_xref.py`):

- **Data source**: nodeblue re-parses a single exported `.L5X` file per call.
  This project builds from the `L5XChunk` objects already produced by
  `SDKPoweredL5XAnalyzer.parse_routine_l5x`, so it covers ACD-sourced projects
  (which never have a standalone `.L5X` file to re-parse) the same way it
  covers L5X-sourced ones.
- **Instruction/tag distinction**: nodeblue filters tokens against a
  hardcoded ~40-mnemonic blacklist. This project instead detects a CALL
  structurally (an identifier immediately followed by `(`), which needs no
  mnemonic list for the primary distinction - a deliberate divergence,
  because this project's own parsed instruction documentation turned out to
  be unsafe to use as a tag-exclusion blacklist (see
  `src/plc_language/mnemonics.py`: 323 of 577 parsed v35 instruction-doc
  entries are glossary/acronym topics with an empty category, including
  names like `PV`, `IO`, `TIMER`, `AXIS`, `REG`, and `HSC` that are also
  extremely common real tag names).
- **Addressing**: this project's tokenizer additionally handles Logix bit
  addresses (`Tag.3`), array indices with identifier indices (`Arr[Idx].Bit`,
  where `Idx` is also indexed as its own reference), and colon-qualified I/O
  and program-scoped tags (`Local:1:I.Data`, `Program:Other.Tag`).
- **Read/write classification**: derived from each parsed instruction's
  mnemonic and operand position (see `_INSTRUCTION_ACCESS` in
  `l5x_xref.py`) - nodeblue's cross-reference does not classify access.

## WhiskeyHouse/ignition-mcp

**Source**: https://github.com/WhiskeyHouse/ignition-mcp
**License**: GNU General Public License v3.0 (full text in `ignition/LICENSE`)

The `ignition/` directory is an unmodified copy of this project (minus its CI
workflows and personal Claude settings), included so the whole MCP toolset
lives in one repo. It remains under GPL-3.0. The rest of this repository is
not derived from it.
