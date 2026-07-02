# branchbreak

[![CI](https://github.com/harryc295/branchbreak/actions/workflows/ci.yml/badge.svg)](https://github.com/harryc295/branchbreak/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Changelog](https://img.shields.io/badge/Changelog-0.2.0-blue.svg)](CHANGELOG.md)

Continuous automated red-teaming for LLMs and AI agents. branchbreak runs an
*attacker model that adapts* — it discovers jailbreaks by iterative refinement
and tree search, scores every finding against MITRE ATLAS, and gates CI/CD with
an exit code. It is an authorized safety-evaluation tool: the shipped objectives
are benign refusal-boundary surrogates, and it runs fully offline or against a
real model.

**[Full write-up: what PAIR and TAP actually buy you](WRITEUP.md)**

Most red-team tooling fires a *fixed* battery of prompts. The interesting
attacks against modern models are not fixed — they are found by an attacker that
reacts to what the target says. branchbreak implements three published
algorithms for that, PAIR, TAP, and Crescendo, behind one CLI with enterprise
reporting, scan history, alerting, and a CI/CD gate on top.

## Why adaptive

A single un-refined attack ("single-shot") is what a static probe list gives
you. It fails against a model with even basic instruction-following. The same
objective falls quickly once an attacker is allowed to observe the refusal and
refine. From the shipped offline scan:

| strategy | what it is | attack success rate |
|---|---|---|
| single-shot | one un-refined prompt (a fixed probe) | 0/3 |
| **PAIR** | one attacker chain, refine on each response | **3/3** |
| **TAP** | branch refinements, prune off-topic, expand best | **3/3** |

That gap is the entire case for adaptive red-teaming, and it is the capability a
fixed-battery tool cannot show. The offline surrogate is deterministic, so this
table demonstrates the *engine's mechanics*, not real-model robustness. Full
analysis, including a multi-trial run against a real model, in
[`results/findings.md`](results/findings.md).

## The algorithms

- **PAIR** — *Prompt Automatic Iterative Refinement* (Chao et al., 2023,
  [arXiv:2310.08419](https://arxiv.org/abs/2310.08419)). One attacker chain:
  propose an attack, observe the target's response, refine, repeat until the
  target breaks or the query budget is spent.
- **TAP** — *Tree of Attacks with Pruning* (Mehrotra et al., 2023,
  [arXiv:2312.02119](https://arxiv.org/abs/2312.02119)). Branch several
  refinements per node, use the judge to prune off-topic candidates *before*
  spending a target query, expand the best, keep the top-*w* frontier. Branching
  raises success rate; pruning keeps it query-efficient.
- **Crescendo** — (Russinovich et al., 2024,
  [arXiv:2404.01833](https://arxiv.org/abs/2404.01833)). Genuinely multi-turn:
  unlike PAIR/TAP, which send the target a fresh single exchange on every
  attempt, Crescendo keeps a real, growing conversation and escalates gradually
  within it — the opening turns can be entirely benign. This is a compact
  implementation; it doesn't include the paper's backtrack-on-refusal step.

All three are steered by a **judge** model that scores responses 1–10, but
ground-truth success is decided by an **oracle**, not the judge. A weak or
gameable judge can only misrank the search — it cannot fabricate a jailbreak.
The test suite asserts exactly this.

**Converters** transform an attack prompt before it reaches the target —
base64, ROT13, leetspeak — the same primitive as PyRIT's Converter classes,
for testing whether obfuscation evades a keyword-based guardrail. Set
`"converters": ["base64"]` in a profile; the attacker's own history keeps the
original, only the target sees the transformed wire form.

## Architecture

```
  profile.json ──► scan orchestrator ──► reports (html / json / md)
  (config-as-code)      │                        │
                        │                   SQLite history ──► trend / export
        ┌───────────────┼───────────────┐        │
        ▼               ▼               ▼   MITRE ATLAS mapping
    attacker ─converters► target       judge
    (adapts)         (under test)  (ranks + prunes)
        └──► PAIR / TAP / Crescendo / single-shot ──► oracle ──► findings ──► risk ──► CI gate ──► webhook alert
   provider: mock (offline) | ollama | openai-compatible | anthropic
```

Every box is a small, testable unit. Providers share one `complete(messages)`
interface, so the same scan runs against a local Ollama model, any
OpenAI-compatible endpoint, the Anthropic Messages API, or a deterministic mock
for CI — no code change, only the profile.

## Install

Standard library only at runtime, no pip dependencies. Not published on PyPI,
but it is a real package — install straight from git if you want the
`branchbreak` console command instead of `python -m branchbreak.cli`:

```
pip install git+https://github.com/harryc295/branchbreak
branchbreak scan --profile profiles/default.json --out results
```

Or just clone it and run the module directly:

```
git clone https://github.com/harryc295/branchbreak
cd branchbreak
python tests/test_branchbreak.py        # 29 tests, offline
```

For development: `pip install -e ".[dev]"` pulls in mypy, ruff, and pytest —
the same checks CI runs (`mypy branchbreak/`, `ruff check branchbreak/ tests/`).

## Run a scan

Offline, against the built-in mock target (no model, no key):

```
python -m branchbreak.cli scan --profile profiles/default.json --out results

# Crescendo vs PAIR/TAP, made concrete: this profile sets a boundary that a
# single message can never reach, so PAIR/TAP hold no matter the budget —
# only Crescendo breaks it, by turn 4, because it accumulates real pressure
# across a growing conversation instead of starting fresh every attempt.
python -m branchbreak.cli scan --profile profiles/crescendo.json --out results-crescendo
```

Against a real model:

```
# local, via Ollama's OpenAI-compatible endpoint
python -m branchbreak.cli scan --provider ollama --model llama3.2:3b --fail-on high

# Anthropic Messages API (reads ANTHROPIC_API_KEY)
python -m branchbreak.cli scan --provider anthropic --model claude-sonnet-5

# any OpenAI-compatible gateway (reads OPENAI_BASE_URL / OPENAI_API_KEY)
python -m branchbreak.cli scan --provider openai --model gpt-4o-mini
```

`--provider` points the attacker, target, and judge at one backend (a model
red-teaming itself); split them in the profile to use a strong attacker against
a weaker target. The command exits non-zero when any finding meets `--fail-on`,
so it drops straight into a pipeline — see
[`examples/github-actions.yml`](examples/github-actions.yml).

Note on real-model runs: target models are typically sampled at temperature
1.0, so results are stochastic. Don't trust a single run — the write-up and
`results/findings.md` report a small multi-trial rate rather than one sample.

Two more flags for production use:

```
# cap total target queries across the whole scan — protects a paid API from
# an unexpectedly expensive run (wide TAP branching over many objectives)
python -m branchbreak.cli scan --max-queries 100

# run (objective, strategy) jobs concurrently instead of sequentially
python -m branchbreak.cli scan --parallel 4
```

`--max-queries` and `--parallel` are mutually exclusive in effect: budget
tracking only knows a job's cost after it finishes, so it can't honor a
running total across concurrent jobs without risking an over-spend —
`--max-queries` runs sequentially regardless of `--parallel`.

## Operations

```
# catch a broken profile.json before it fails mid-scan
python -m branchbreak.cli validate --profile profiles/default.json

# attack success rate over scan history — the "is our ASR rising release
# over release" the README used to just promise is one query away
python -m branchbreak.cli trend --db branchbreak.db

# CSV export of every scan/run/finding for audit evidence (SOC 2 / ISO 27001)
python -m branchbreak.cli export --db branchbreak.db --out evidence/
```

Post to Slack (or any Slack-compatible webhook) when a scan's gate fails:

```
python -m branchbreak.cli scan --webhook https://hooks.slack.com/services/...
# or set BRANCHBREAK_WEBHOOK_URL instead of passing --webhook every time
```

## Reports

Each scan writes three artifacts:

- `report.html` — a self-contained dashboard: risk score, ASR by strategy, and
  every finding with its winning attack prompt, the target's response, and the
  ATLAS technique.
- `report.json` — machine-readable, for pipelines and trend tracking.
- `report.md` — for the repo or a writeup.

Scan history persists to SQLite — see `trend` and `export` above.

## Safety and scope

This is a tool for **authorized** safety evaluation, built the way the research
is published:

- **Benign surrogates by default.** The shipped objectives guard a harmless
  canary token; success means the token leaked. This measures whether adaptive
  attacks defeat an instruction boundary without producing harmful content.
- **Objective-agnostic engine.** `taxonomy.py` loads a JSON file of
  user-supplied objectives into the same shape the built-in three use — see
  [`profiles/custom-objectives.example.json`](profiles/custom-objectives.example.json).
  For an authorized engagement against real harm categories, point it at
  objectives sourced from a standard taxonomy (HarmBench, AdvBench,
  JailbreakBench) with a content-classifier oracle. This repo doesn't ship
  that content — the loader is the mechanism, bring your own taxonomy file
  under an authorized engagement. The search, judge, scoring, and reporting
  are unchanged either way.
- **Findings map to MITRE ATLAS**, the framework AI security teams and buyers
  already use. (Technique links point to the ATLAS root site rather than a
  per-technique deep link — atlas.mitre.org is a client-rendered SPA on
  GitHub Pages with no server-side fallback for direct navigation, so every
  deep link currently 404s regardless of the URL.)

Use it only against systems you are authorized to test.

## Layout

```
branchbreak/search.py       PAIR, TAP, Crescendo, single-shot — the adaptive engine
branchbreak/attacker.py     attacker prompt construction, seeded with strategies
branchbreak/converters.py   base64 / rot13 / leetspeak prompt transforms
branchbreak/judge.py        response scoring + on-topic pruning signal
branchbreak/objectives.py   benign refusal-boundary surrogates + success oracle
branchbreak/taxonomy.py     loader for user-supplied objective sets (JSON)
branchbreak/providers.py    mock / ollama / openai-compatible / anthropic (retry + backoff)
branchbreak/atlas.py        MITRE ATLAS catalog + mapping
branchbreak/validate.py     profile.json schema validation
branchbreak/alert.py        Slack-compatible webhook alerting on a failed gate
branchbreak/scoring.py      findings, risk score, CI gate
branchbreak/store.py        SQLite scan history, trend queries, CSV export
branchbreak/report.py       html / json / markdown reports
branchbreak/scan.py         orchestration — query budget cap, parallel execution
branchbreak/cli.py          command line: scan, validate, trend, export
profiles/                   scan profiles (config-as-code)
results/findings.md         research writeup + how to reproduce on real models
tests/                      correctness tests for search, judge, scoring, atlas
```

## License

MIT — see [LICENSE](LICENSE).
