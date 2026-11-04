"""Lints Still's own skills and role briefs (still/Assets): every skill has its front matter and the workflow sections,
and no skill or brief names a tool Still doesn't have or an app without saying it must be connected.
Run: python tests/skilllint.py [repo root]. Exits 1 on any problem."""
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent
ASSETS = ROOT / "still" / "Assets"
SECTIONS = ["When", "Inputs", "Steps", "Check", "Deliverable", "If it goes wrong", "Limits"]
# The tools Still's MCP server offers, read from its source so the list can't drift.
TOOLS = set(re.findall(r'Tool\("([a-z_]+)"', (ROOT / "still" / "McpServer.cs").read_text(encoding="utf-8")))
# Apps a companion reaches only through a connected plugin: a mention must say so on the same line.
APPS = ["Gmail", "Google Calendar", "Outlook", "Slack", "HubSpot", "Salesforce", "Notion", "Linear", "Jira", "Mailchimp", "Google Drive", "Google Sheets", "Stripe"]
problems = []


def lint_text(name, text):
    for word in sorted(set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", text))):
        if word not in TOOLS:
            problems.append(f"{name}: names a tool Still doesn't have: {word}")
    for line in text.splitlines():
        for app in APPS:
            if app in line and "connect" not in line:
                problems.append(f"{name}: mentions {app} without saying it must be connected")
    if "—" in text:
        problems.append(f"{name}: has an em dash")


skills = sorted((ASSETS / "roles").glob("*/skills/*.md")) + [ASSETS / "skills" / "setup.md"]
for f in skills:
    name = str(f.relative_to(ROOT))
    text = f.read_text(encoding="utf-8").replace("\r\n", "\n")
    head = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not head:
        problems.append(f"{name}: no front matter")
        continue
    keys = dict(line.split(":", 1) for line in head.group(1).splitlines() if ":" in line)
    for key in ("name", "description", "when"):
        if not keys.get(key, "").strip():
            problems.append(f"{name}: no {key}")
    found = re.findall(r"^## (.+)$", text, re.M)
    if found != SECTIONS:
        problems.append(f"{name}: sections are {found}, should be {SECTIONS}")
    for section, body in zip(found, re.split(r"^## .+$", text, flags=re.M)[1:]):
        if not body.strip():
            problems.append(f"{name}: {section} is empty")
    lint_text(name, text)
for f in sorted((ASSETS / "roles").glob("*.md")):
    lint_text(str(f.relative_to(ROOT)), f.read_text(encoding="utf-8"))

print(f"{len(skills)} skills, {len(TOOLS)} tools")
for p in problems:
    print("FAIL", p)
print("PASSED" if not problems else f"FAILED {len(problems)}")
sys.exit(1 if problems else 0)
