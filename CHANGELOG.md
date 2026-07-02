# Changelog

## 0.2.0

Renamed from `redforge` — the old name collided with an existing, unrelated
PyPI package doing the same category of work.

Added:
- **Crescendo** (Russinovich et al., 2024, arXiv:2404.01833) — a third
  adaptive strategy, genuinely multi-turn: the target keeps real conversation
  state across turns, unlike PAIR/TAP's fresh-attempt-per-iteration design.
  `profiles/crescendo.json` demonstrates this concretely: PAIR/TAP structurally
  cannot break its boundary, Crescendo does, by turn 4.
- Prompt converters (base64, ROT13, leetspeak) — PyRIT-style prompt transforms
  applied at the delivery layer, for testing whether obfuscation evades a
  keyword-based guardrail.
- A JSON taxonomy loader (`taxonomy.py`) so "point the engine at a real harm
  taxonomy under an authorized engagement" is a config change, not just a
  documentation claim — no harmful content shipped, bring your own file.
- A per-scan query budget cap (`--max-queries`).
- Parallel scan execution (`--parallel`).
- Retry with exponential backoff on transient HTTP failures (429/5xx/timeout).
- Profile schema validation (`branchbreak validate`), including a preflight
  check that a required API key is actually set before a scan starts.
- SQLite-backed `trend` (ASR over scan history) and `export` (CSV audit
  evidence) CLI commands.
- Slack-compatible webhook alerting on a failed gate.
- `pyproject.toml` — installable via `pip install git+https://...` with a
  `branchbreak` console script (not published to PyPI).
- mypy and ruff in CI.

Fixed:
- MITRE ATLAS technique links 404'd (their site is a client-rendered SPA on
  GitHub Pages with no server-side fallback for deep links — not fixable on
  this end; links now point to the working root site).
- The GitHub Actions example referenced a nonexistent `profiles/production.json`
  and `pip install redforge`, which would have installed the unrelated PyPI
  package rather than this tool.

Changed:
- The real-model result in `results/findings.md` and `WRITEUP.md` now reports
  an aggregate across five independent runs instead of a single sample — the
  original one-run result didn't reproduce on a second run.

## 0.1.0

Initial release (as `redforge`). PAIR and TAP behind one CLI, MITRE ATLAS
mapping, risk scoring, CI/CD gate, HTML/JSON/Markdown reports, SQLite scan
history. Four providers (mock/Ollama/OpenAI-compatible/Anthropic).
