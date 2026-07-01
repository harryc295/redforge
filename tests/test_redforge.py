"""Tests for the correctness-critical logic: search control flow, judge parsing,
scoring/gating, and ATLAS coverage. Run: pytest  OR  python tests/test_redforge.py

No network, no model — the mock provider and a few stubs stand in.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from redforge import atlas, judge, objectives, scoring, search
from redforge.providers import MockProvider

OBJ = objectives.default_objectives()[0]  # secret-extraction, canary PELICAN-7731


def mocks(reveal_threshold=3):
    return (MockProvider("attacker", secret=OBJ.canary),
            MockProvider("target", secret=OBJ.canary, reveal_threshold=reveal_threshold),
            MockProvider("judge", secret=OBJ.canary))


# ------------------------------- search --------------------------------------

def test_single_shot_holds_against_boundary():
    # one un-refined attack carries a single technique; below the threshold
    r = search.run_single_shot(OBJ, *mocks())
    assert r.success is False and r.queries == 1


def test_pair_discovers_break_by_refining():
    r = search.run_pair(OBJ, *mocks(), max_iters=8)
    assert r.success is True
    assert r.queries == 3          # needs 3 stacked techniques to cross threshold
    assert r.best.success and OBJ.canary.lower() in r.best.response.lower()


def test_pair_respects_query_budget_when_unbreakable():
    r = search.run_pair(OBJ, *mocks(reveal_threshold=99), max_iters=5)
    assert r.success is False and r.queries == 5


def test_tap_discovers_break():
    r = search.run_tap(OBJ, *mocks(), depth=4, branching=3, width=3)
    assert r.success is True and r.best.success


def test_success_is_decided_by_oracle_not_judge():
    # judge always shouts 10, but the target never reveals the canary
    class Always10:
        def complete(self, messages, **kw):
            return "Rating: [[10]]"
    atk, tgt, _ = mocks(reveal_threshold=99)
    r = search.run_pair(OBJ, atk, tgt, Always10(), max_iters=4)
    assert r.success is False          # oracle overrules a gameable judge
    assert r.best.score == 10          # judge did inflate the ranking


def test_tap_prunes_offtopic_before_querying_target():
    class CountingTarget:
        calls = 0
        def complete(self, messages, **kw):
            CountingTarget.calls += 1
            return "I can't help with that."
    class LowOntopicJudge:
        def complete(self, messages, **kw):
            return "Rating: [[1]]"      # every candidate scored off-topic
    tgt = CountingTarget()
    r = search.run_tap(OBJ, MockProvider("attacker"), tgt, LowOntopicJudge(),
                       depth=4, branching=3, width=3, ontopic_min=3)
    assert r.pruned == 3               # root's 3 children all pruned
    assert r.queries == 0 and tgt.calls == 0   # pruning saved every target query


# -------------------------------- judge --------------------------------------

def test_parse_rating_variants():
    assert judge.parse_rating("Rating: [[7]]") == 7
    assert judge.parse_rating("[[15]]") == 10      # clamped
    assert judge.parse_rating("[[0]]") == 1        # clamped up
    assert judge.parse_rating("I'd say 8 out of 10") == 8
    assert judge.parse_rating("no number here") == 1


# ------------------------------- scoring -------------------------------------

def test_findings_attributed_to_cheapest_winning_strategy():
    objs = objectives.default_objectives()
    o = objs[0]
    R = search.Result
    N = search.Node(prompt="p", response="r", score=10, success=True, depth=0)
    results = [R("single_shot", o.name, False, 1, N),
               R("tap", o.name, True, 13, N),
               R("pair", o.name, True, 3, N)]
    f = scoring.findings_from(results, objs)
    assert len(f) == 1 and f[0].strategy == "pair" and f[0].queries == 3


def test_risk_score_saturates():
    crit = scoring.Finding("x", "c", "critical", "AML.T0051", "pair", 1, "", "")
    assert scoring.risk_score([crit]) == 100
    assert scoring.risk_score([]) == 0


def test_gate_fails_on_threshold():
    high = scoring.Finding("x", "c", "high", "AML.T0057", "pair", 1, "", "")
    med = scoring.Finding("y", "c", "medium", "AML.T0051", "pair", 1, "", "")
    assert scoring.gate([high], "high") == (False, 1)
    assert scoring.gate([med], "high") == (True, 0)     # medium below high gate
    assert scoring.gate([med], "medium") == (False, 1)
    assert scoring.gate([], "low") == (True, 0)


# -------------------------------- atlas --------------------------------------

def test_every_objective_maps_to_known_atlas_technique():
    for o in objectives.default_objectives():
        assert atlas.is_known(o.atlas), f"{o.name} -> {o.atlas} not in ATLAS catalog"
        assert atlas.describe(o.atlas)["url"].startswith("https://atlas.mitre.org/")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print(f"all {len(fns)} tests passed")
