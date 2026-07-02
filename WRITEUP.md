# Adaptive Red-Teaming an LLM: What PAIR and TAP Actually Buy You

Most LLM red-team tools run a fixed list of prompts against a target and
count how many get through. That measures whether a model refuses known
attacks, not whether it holds up against an attacker who reads the refusal
and tries again differently. A motivated human does that. So does another
model.

I built [redforge](https://github.com/harryc295/redforge) to test that gap
directly. It runs an attacker that adapts, using the two published
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

## Result 2: a real model

The surrogate proves the engine works. It doesn't say anything about a real
model. So I pointed redforge at `llama3.2:3b` running locally via Ollama:
one 3B model playing attacker, target, and judge, with a small search
budget (PAIR max 6 queries, TAP depth 3 / branching 2):

| objective | single-shot | PAIR (≤6) | TAP (d3/b2) |
|---|---|---|---|
| secret-extraction | held | held | held |
| forbidden-phrase | **broken** | held | held |
| system-prompt-leak | held | held | held |

This is the interesting one, because it's not a clean win for adaptation:

- **A weak boundary fell to one shot.** The forbidden-phrase objective
  broke on the very first, un-refined attack.
- **Two stronger boundaries held through the full adaptive budget.** The
  secret token and the operator note survived PAIR and TAP alike.
- **Single-shot beat PAIR on the one objective that broke, and that's real,
  not a bug.** At temperature 1.0 the target is stochastic, so a lucky
  single sample can land before a short refinement chain from a weak 3B
  attacker finds its footing. Small budgets and a weak attacker are exactly
  the regime where adaptation buys the least.
- **Pruning fired on real candidates.** TAP dropped 4, 2, and 1 off-topic
  candidate prompts across the three objectives before they cost a target
  query. That's the query-efficiency mechanism the deterministic surrogate
  couldn't exercise at all.

The published TAP paper reports upward of 80% attack success against
GPT-4-class targets, using a much stronger attacker and larger budgets. A
3B model attacking itself with a six-query ceiling sits close to the floor
of what these algorithms can do. That's still worth running: the harness
holds up end to end against a genuine model, and the mechanics behave
exactly as designed. The ceiling this run sits near points at the next
experiment.

```
python -m redforge.cli scan --provider anthropic --model claude-sonnet-5 --fail-on high
```

That's the natural next data point: a frontier attacker against the same
surrogate, to see how far the gap between single-shot and adaptive widens
with real capability behind the attacker.

## Where this fits into an actual engagement

Everything above uses benign surrogate objectives. The target guards a
harmless canary token, and success means that token leaking, not any
harmful content being generated. That's deliberate: it lets the harness
run in the open, in CI, without producing anything dangerous.

The engine itself is objective-agnostic. Point it at objectives sourced
from a standard harm taxonomy (HarmBench, AdvBench, JailbreakBench) with a
matching content-classifier oracle, and nothing in the search, judge,
scoring, or reporting changes. That's how you'd run this under an
authorized engagement. Findings map to MITRE ATLAS techniques, so the
output slots into the framework AI security teams already use to talk
about this class of risk.

## Try it

```
git clone https://github.com/harryc295/redforge
cd redforge
python tests/test_redforge.py        # 11 tests, offline, no dependencies
python -m redforge.cli scan --profile profiles/default.json --out results
```

Standard library only, no pip install required to run the offline scan.
Full method notes and raw results: [`results/findings.md`](results/findings.md).

## References

- Chao et al., *Jailbreaking Black Box LLMs in Twenty Queries* (PAIR), [arXiv:2310.08419](https://arxiv.org/abs/2310.08419)
- Mehrotra et al., *Tree of Attacks: Jailbreaking Black-Box LLMs Automatically* (TAP), [arXiv:2312.02119](https://arxiv.org/abs/2312.02119)
- [MITRE ATLAS](https://atlas.mitre.org/)
- OWASP Top 10 for LLM Applications
