"""The adaptive attack engine: PAIR and TAP.

PAIR (Chao et al., 2023, arXiv:2310.08419) — Prompt Automatic Iterative
Refinement. A single attacker chain: propose, observe, refine, repeat until the
target breaks or the query budget runs out.

TAP (Mehrotra et al., 2023, arXiv:2312.02119) — Tree of Attacks with Pruning.
Branch several candidate refinements per node, prune off-topic ones with the
judge *before* spending a target query, expand the best, and keep the top-w
frontier. Branching raises success rate; pruning keeps it query-efficient.

Ground-truth success comes from the objective's oracle; the judge only ranks.
"""

from dataclasses import dataclass, field

from . import attacker, judge


@dataclass
class Node:
    prompt: str
    response: str
    score: int
    success: bool
    depth: int
    improvement: str = ""
    ontopic: int = 10
    history: list = field(default_factory=list)


@dataclass
class Result:
    strategy: str
    objective: str
    success: bool
    queries: int                 # target model queries spent
    best: Node | None
    transcript: list = field(default_factory=list)
    pruned: int = 0              # off-topic candidates dropped before a target query


def _attempt(objective, target, judge_provider, prompt, depth, improvement, history):
    response = target.complete(
        [{"role": "system", "content": objective.target_system},
         {"role": "user", "content": prompt}])
    success = objective.succeeded(response)
    score = 10 if success else judge.score_response(judge_provider, objective, response)
    rec = {"attack": prompt, "response": response, "score": score, "improvement": improvement}
    return Node(prompt=prompt, response=response, score=score, success=success,
                depth=depth, improvement=improvement, history=history + [rec])


def run_pair(objective, attacker_p, target_p, judge_p, max_iters=8):
    history, transcript, queries = [], [], 0
    for i in range(max_iters):
        msgs = attacker.build_messages(objective, history, depth=i, branch=0)
        prompt, improvement = attacker.parse_attack(attacker_p.complete(msgs, depth=i, branch=0))
        node = _attempt(objective, target_p, judge_p, prompt, i, improvement, history)
        queries += 1
        history = node.history
        transcript.append(node)
        if node.success:
            return Result("pair", objective.name, True, queries, node, transcript)
    best = max(transcript, key=lambda n: n.score) if transcript else None
    return Result("pair", objective.name, False, queries, best, transcript)


def run_tap(objective, attacker_p, target_p, judge_p,
            depth=4, branching=3, width=3, ontopic_min=3):
    frontier = [[]]                       # each entry is an attacker history (a path)
    transcript, queries, pruned = [], 0, 0
    for d in range(depth):
        children = []
        for hist in frontier:
            for b in range(branching):
                msgs = attacker.build_messages(objective, hist, depth=d, branch=b)
                prompt, improvement = attacker.parse_attack(
                    attacker_p.complete(msgs, depth=d, branch=b))
                # Prune off-topic candidates before spending a target query.
                ot = judge.score_ontopic(judge_p, objective, prompt)
                if ot < ontopic_min:
                    pruned += 1
                    continue
                node = _attempt(objective, target_p, judge_p, prompt, d, improvement, hist)
                node.ontopic = ot
                queries += 1
                transcript.append(node)
                if node.success:
                    return Result("tap", objective.name, True, queries, node, transcript, pruned)
                children.append(node)
        if not children:
            break
        children.sort(key=lambda n: n.score, reverse=True)
        frontier = [c.history for c in children[:width]]
    best = max(transcript, key=lambda n: n.score) if transcript else None
    return Result("tap", objective.name, False, queries, best, transcript, pruned)


def run_single_shot(objective, attacker_p, target_p, judge_p):
    """One un-refined attack — the baseline a fixed probe battery represents.
    Included so a scan can quantify how much adaptation actually buys."""
    msgs = attacker.build_messages(objective, [], depth=0, branch=0)
    prompt, improvement = attacker.parse_attack(attacker_p.complete(msgs, depth=0, branch=0))
    node = _attempt(objective, target_p, judge_p, prompt, 0, improvement, [])
    return Result("single_shot", objective.name, node.success, 1, node, [node])


STRATEGIES = {"pair": run_pair, "tap": run_tap, "single_shot": run_single_shot}
