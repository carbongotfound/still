# Agents

Still runs the AI apps people already pay for. Built in: Claude (Claude Code), ChatGPT (OpenAI's CLI) and Grok (Grok Build).
Each is an `AgentAdapter` in `still/Agents/AgentAdapter.cs`; their JSON lines become `AgentEvent`s in `AgentStream.cs`.

## More agents: manifests

Any CLI can be added with a JSON file in `%LOCALAPPDATA%\Still\agents\`. Still writes disabled examples there the first time
(Gemini, Cursor Agent, OpenCode, Aider). They are untested; set `"enabled": true` to try one.

| Field | Meaning |
|---|---|
| `id`, `name`, `command` | Required. `id` is lowercase letters, digits and dashes. |
| `detect`, `expect` | Args to run, and a regex the output must match to count as signed in. |
| `signin`, `domains` | Args that sign in, and the only sites a sign-in link may be on. |
| `install`, `site` | Shown under "How to install". Still never runs `install` itself. |
| `run`, `resume`, `model`, `effort` | Args. Placeholders: `{prompt}` `{promptFile}` `{model}` `{effort}` `{cwd}` `{mcpConfig}` `{session}`. Without a prompt placeholder the prompt goes on stdin. `{prompt}` is refused for `.cmd` launchers. |
| `mcpFile` | Also copy Still's MCP config to this path inside the run folder, for apps that read a fixed file. |
| `output` | `stream-json` (Anthropic events), `jsonl` with `fields`, or `plain` (each line joins the reply). |
| `fields` | For `jsonl`: `session`, `text`, `delta`, `tool`, `toolId`, `toolArgs`, `error`, each `"path"` or `"path when key=value,key2=value2"`. |

Every run strips API-key variables, lives in a Job Object (Stop ends the whole tree), stops after an hour, and keeps
a log of failed runs in `ai/logs` (never the prompt).

## Tests

- `dotnet run --project tests/Still.AgentChecks -- .` parses recorded and hand-written output in `tests/fixtures/agents`.
- `python tests/desktop/providers.py <exe>` drives fake manifest agents: onboarding states, a run, resume, API keys, Stop.
- `python tests/desktop/live.py <exe> claude` runs one real task on your plan. By hand only.
- `python tests/desktop/takeover.py <exe>` checks the controls over an AI's page: the pill, Take over, Hand back, Stop.
  `--live` adds one small Claude run with a takeover in the middle. By hand only.
