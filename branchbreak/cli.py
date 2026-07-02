"""branchbreak command line.

    python -m branchbreak.cli scan --profile profiles/default.json --out results
    python -m branchbreak.cli scan --provider ollama --model qwen2.5:7b --fail-on high
    python -m branchbreak.cli validate --profile profiles/default.json
    python -m branchbreak.cli trend --db branchbreak.db
    python -m branchbreak.cli export --db branchbreak.db --out evidence/

Exit code of `scan` is the CI gate: non-zero if any finding meets --fail-on severity.
"""

import argparse
import os
import sys

from . import alert, report, scan, store, validate as validate_mod


def _cmd_scan(args):
    profile = scan.load_profile(args.profile)
    if args.fail_on:
        profile["fail_on"] = args.fail_on
    # Apply --provider/--model before validating: otherwise a CLI override to
    # e.g. anthropic wouldn't be visible to the preflight API-key check, which
    # only sees whatever's already in the profile file's own provider blocks.
    scan.apply_provider_override(profile, args.provider, args.model)

    problems = validate_mod.validate(profile)
    if problems:
        print("profile is invalid:")
        for p in problems:
            print(f"  - {p}")
        return 2

    if args.max_queries is not None and args.parallel > 1:
        print(f"note: --max-queries forces sequential execution "
              f"(ignoring --parallel {args.parallel})")

    summary = scan.run_scan(profile, provider=args.provider, model=args.model,
                            max_queries=args.max_queries, parallel=args.parallel)

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "report.html"), "w", encoding="utf-8") as f:
        f.write(report.to_html(summary))
    with open(os.path.join(args.out, "report.json"), "w", encoding="utf-8") as f:
        f.write(report.to_json(summary))
    with open(os.path.join(args.out, "report.md"), "w", encoding="utf-8") as f:
        f.write(report.to_markdown(summary))

    if args.db:
        conn = store.connect(args.db)
        sid = store.save_scan(conn, summary["target"], args.profile, summary["results"],
                              summary["findings"], summary["risk"], summary["passed"])
        print(f"scan #{sid} saved to {args.db}")

    _print_summary(summary, args.out)

    if not summary["passed"] and args.webhook:
        alert.send(args.webhook, summary)

    return summary["exit_code"]


def _cmd_validate(args):
    profile = scan.load_profile(args.profile)
    problems = validate_mod.validate(profile)
    if not problems:
        print(f"{args.profile}: valid")
        return 0
    print(f"{args.profile}: {len(problems)} problem(s):")
    for p in problems:
        print(f"  - {p}")
    return 1


def _cmd_trend(args):
    conn = store.connect(args.db)
    rows = store.asr_trend(conn, limit=args.limit)
    if not rows:
        print(f"no scan history in {args.db}")
        return 0
    print(f"{'scan':<6}{'ts':<27}{'target':<16}{'risk':<7}by strategy")
    print("-" * 83)
    for r in rows:
        strat_summary = "  ".join(f"{s}:{v['asr']:.0%}({v['n']})"
                                  for s, v in r["by_strategy"].items())
        print(f"{r['scan_id']:<6}{r['ts']:<27}{r['target']:<16}{r['risk']:<7}{strat_summary}")
    return 0


def _cmd_export(args):
    conn = store.connect(args.db)
    paths = store.export_csv(conn, args.out)
    for p in paths:
        print(f"wrote {p}")
    return 0


def _print_summary(summary, out):
    print(f"\ntarget: {summary['target']}   risk: {summary['risk']}/100   "
          f"gate: {'PASS' if summary['passed'] else 'FAIL'} (fail-on {summary['fail_on']})")
    print(f"{'objective':<22}{'strategy':<14}{'result':<9}{'queries':<8}pruned")
    print("-" * 62)
    for r in summary["results"]:
        res = "SKIP" if r.skipped else ("BROKEN" if r.success else "held")
        print(f"{r.objective:<22}{r.strategy:<14}{res:<9}{r.queries:<8}{r.pruned}")
    print("-" * 62)
    if summary["findings"]:
        print(f"{len(summary['findings'])} finding(s):")
        for f in summary["findings"]:
            print(f"  [{f.severity}] {f.objective} - broken by {f.strategy} "
                  f"in {f.queries} queries ({f.atlas})")
    print(f"\nreports written to {out}/ (report.html, report.json, report.md)")


def main(argv=None):
    p = argparse.ArgumentParser(prog="branchbreak")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="run a red-team scan")
    s.add_argument("--profile", default="profiles/default.json")
    s.add_argument("--out", default="results")
    s.add_argument("--provider", choices=["mock", "ollama", "openai", "anthropic"])
    s.add_argument("--model")
    s.add_argument("--fail-on", choices=["low", "medium", "high", "critical"])
    s.add_argument("--db", default="branchbreak.db", help="SQLite path; empty to skip")
    s.add_argument("--max-queries", type=int, default=None,
                   help="stop starting new (objective, strategy) runs once this many "
                        "target queries have been spent across the scan")
    s.add_argument("--parallel", type=int, default=1,
                   help="run this many (objective, strategy) jobs concurrently "
                        "(ignored when --max-queries is set)")
    s.add_argument("--webhook", default=os.environ.get("BRANCHBREAK_WEBHOOK_URL"),
                   help="Slack-compatible webhook URL to notify on a failed gate")
    s.set_defaults(func=_cmd_scan)

    v = sub.add_parser("validate", help="check a profile.json for problems")
    v.add_argument("--profile", default="profiles/default.json")
    v.set_defaults(func=_cmd_validate)

    t = sub.add_parser("trend", help="show attack success rate over scan history")
    t.add_argument("--db", default="branchbreak.db")
    t.add_argument("--limit", type=int, default=20)
    t.set_defaults(func=_cmd_trend)

    e = sub.add_parser("export", help="export scan history to CSV for audit evidence")
    e.add_argument("--db", default="branchbreak.db")
    e.add_argument("--out", default="evidence")
    e.set_defaults(func=_cmd_export)

    args = p.parse_args(argv)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
