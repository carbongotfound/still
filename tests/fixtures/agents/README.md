Agent CLI output that Still's parsers are checked against (`tests/Still.AgentChecks`).

- `claude.jsonl`: recorded from Claude Code 2.1.312 on 2026-10-28 (`-p --output-format stream-json --verbose`, Still's MCP only), asked to open example.com and give its title. The init line is trimmed to the fields Still reads, so no local paths are kept.
- `grok.jsonl`, `chatgpt.jsonl`: written by hand in each CLI's documented format (Grok Build `streaming-messages-json`, ChatGPT's CLI `exec --json`), because neither app is signed in on the build PC. Replace them with recordings once they are.
- `gemini.jsonl`, `opencode.jsonl`: recorded on 2026-11-02 from the real Gemini CLI 0.66.0 (`--output-format stream-json`) and OpenCode 1.19.5 (`run --format json`), each pointed at Still's fake model server (`tests/desktop/fakemodels.py`) with a throwaway key and only Still's MCP server, so no account was used. Each has one Still tool call that failed and a reply.
- `manifest-jsonl.jsonl`: a generic JSON-lines agent, read through a manifest field map.
