# Adaptive Red-Teaming an LLM: What PAIR and TAP Actually Buy You

Most LLM red-team tools run a fixed list of prompts against a target and
count how many get through. That measures whether a model refuses known
attacks, not whether it holds up against an attacker who reads the refusal
and tries again differently. A motivated human does that. So does another
model.

I built [branchbreak](https://github.com/harryc295/branchbreak) to test that
gap directly. It runs an attacker that adapts, using the two published
algorithms for doing it: PAIR and TAP, instead of a static probe list.

## The two algorithms

**PAIR** (Chao et al., 2023,
[arXiv:2310.08419](https://arxiv.org/abs/2310.08419)) runs one attacker
chain: propose an attack, read the target's response, refine, repeat until
the target breaks or the budget runs out.

**TAP** (Mehrotra et al., 2023,
[arXiv:2312.02119](https://arxiv.org/abs/2312.02119)) branches several
refinements per node, uses a judge model to prune off-topic candidates
before they cost a query against the target, and expands the strongest
branch. Branching raises the success rate. Pruning keeps it query-efficient.

Both are steered by a judge that scores responses 1–10. Ground truth is
decided by an oracle, not the judge. A weak or gameable judge can misrank
the search; it cannot fabricate a finding. I wrote a test that asserts
exactly that, because a red-team tool whose "success" signal can be gamed
by its own scorer isn't measuring anything.

## Result 1: a controlled surrogate

Against a deterministic refusal-boundary target (guarding a benign canary
token, no harmful content generated, just testing whether the boundary
holds):

| objective | single-shot | PAIR | TAP |
|---|---|---|---|
| secret-extraction | held | broken (3 queries) | broken |
| forbidden-phrase | held | broken (3 queries) | broken |
| system-prompt-leak | held | broken (3 queries) | broken |

Single-shot: 0/3. Adaptive: 3/3. That table makes the entire case for
adaptive red-teaming, and it's a case a fixed-battery tool structurally
cannot make: it never gets to observe and refine.

One honest wrinkle: PAIR beat TAP on query count here (3 vs. 13). The
surrogate yields as soon as an attack stacks enough distinct techniques, so
a single refining chain is already optimal. TAP's branching is wasted
against a target that never stalls or drifts. TAP's advantages (higher
success rate where a single chain gets stuck, and query savings from
pruning dead branches) only show up against targets that stall. The
pruning mechanism itself is real and tested
(`test_tap_prunes_offtopic_before_querying_target`); the surrogate doesn't
exercise it.

## Result 2: a real model, five times

The surrogate proves the engine works. It doesn't say anything about a real
model. So I pointed branchbreak at `llama3.2:3b` running locally via Ollama:
one 3B model playing attacker, target, and judge, small search budget (PAIR
max 6 queries, TAP depth 3 / branching 2).

The target samples at temperature 1.0, so a single run is an anecdote, not a
rate. I ran the identical command five times. Aggregate attack success rate
(15 attempts per strategy, 5 runs × 3 objectives):

| strategy | broke | ASR |
|---|---|---|
| single-shot | 1/15 | 7% |
| PAIR | 2/15 | 13% |
| TAP | 1/15 | 7% |

This is the interesting one, because it doesn't tell a clean story:

- **Which objective broke, and which strategy broke it, changed almost every
  run.** Run 1: forbidden-phrase fell to a single un-refined attack. Runs 3
  and 4: secret-extraction fell to PAIR (and once to TAP too). Two of five
  runs broke nothing at all. A single run reported as "the" result — which is
  what the first version of this write-up did — is a sample being reported as
  a rate.
- **One thing held up every single run: TAP's pruning.** It dropped
  between 4 and 11 off-topic candidates per run (out of up to 18 possible)
  before they cost a target query, on all five runs, independent of whether
  anything actually broke. That's a mechanism claim, not an outcome claim,
  and it's the part of this result actually worth trusting from five runs.
- **A high-severity CI gate would have failed 2 of 5 runs.** Only
  secret-extraction is high-severity; the one run where forbidden-phrase
  broke (medium) wouldn't have tripped a `--fail-on high` gate on its own.

The published TAP paper reports upward of 80% attack success against
GPT-4-class targets, using a much stronger attacker and larger budgets. A 3B
model attacking itself with a six-query ceiling sits close to the floor of
what these algorithms can do — a 7-13% aggregate ASR is consistent with that
floor, not a contradiction of it. Raw output for all five runs is committed
under `results-ollama-trials/`; full numbers and method notes in
[`results/findings.md`](results/findings.md).

```
python -m branchbreak.cli scan --provider anthropic --model claude-sonnet-5 --fail-on high
```

That's the natural next data point: a frontier attacker against the same
surrogate, to see how far the gap between single-shot and adaptive widens
with real capability behind the attacker.

## Where this fits into an actual engagement

Everything above uses benign surrogate objectives. The target guards a
harmless canary token, and success means that token leaking, not any
harmful content being generated. That's deliberate: it lets the harness
run in the open, in CI, without producing anything dangerous.

The engine itself is objective-agnostic: `taxonomy.py` loads a JSON file of
user-supplied objectives into the same shape the built-in three use, so
pointing it at a standard harm taxonomy (HarmBench, AdvBench, JailbreakBench)
under an authorized engagement is a config change, not a code change — see
`profiles/custom-objectives.example.json` for the schema. Findings map to
MITRE ATLAS techniques, so the output slots into the framework AI security
teams already use to talk about this class of risk.

## Try it

```
git clone https://github.com/harryc295/branchbreak
cd branchbreak
python tests/test_branchbreak.py     # 29 tests, offline, no dependencies
python -m branchbreak.cli scan --profile profiles/default.json --out results
```

Standard library only, no pip install required to run the offline scan.
Full method notes and raw results: [`results/findings.md`](results/findings.md).

## References

- Chao et al., *Jailbreaking Black Box LLMs in Twenty Queries* (PAIR), [arXiv:2310.08419](https://arxiv.org/abs/2310.08419)
- Mehrotra et al., *Tree of Attacks: Jailbreaking Black-Box LLMs Automatically* (TAP), [arXiv:2312.02119](https://arxiv.org/abs/2312.02119)
- Russinovich et al., *Great, Now Write an Article About That: The Crescendo Multi-Turn LLM Jailbreak Attack*, [arXiv:2404.01833](https://arxiv.org/abs/2404.01833)
- [MITRE ATLAS](https://atlas.mitre.org/)
- OWASP Top 10 for LLM Applications
