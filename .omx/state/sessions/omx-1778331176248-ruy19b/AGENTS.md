<!-- OMX:RUNTIME:START -->
<session_context>
**Session:** omx-1778331176248-ruy19b | 2026-05-09T12:52:59.979Z

**Codebase Map:**
  backend/: auto-render, auto-render.min, auto-render, copy-tex, copy-tex.min, copy-tex, mathtex-script-type, mathtex-script-type.min, mathtex-script-type, mhchem
  frontend/: pdf.worker.min, agent, auth, chat, document, documentProject, folder, main

**Explore Command Preference:** enabled via `USE_OMX_EXPLORE_CMD` (default-on; opt out with `0`, `false`, `no`, or `off`)
- Advisory steering only: agents SHOULD treat `omx explore` as the default first stop for direct inspection and SHOULD reserve `omx sparkshell` for qualifying read-only shell-native tasks.
- For simple file/symbol lookups, use `omx explore` FIRST before attempting full code analysis.
- When the user asks for a simple read-only exploration task (file/symbol/pattern/relationship lookup), strongly prefer `omx explore` as the default surface.
- Explore examples: `omx explore...

**Compaction Protocol:**
Before context compaction, preserve critical state:
1. Write progress checkpoint via state_write MCP tool
2. Save key decisions to notepad via notepad_write_working
3. If context is >80% full, proactively checkpoint state
</session_context>
<!-- OMX:RUNTIME:END -->
