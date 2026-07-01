"""redforge command line.

    python -m redforge.cli scan --profile profiles/default.json --out results
    python -m redforge.cli scan --provider ollama --model qwen2.5:7b --fail-on high

Exit code is the CI gate: non-zero if any finding meets --fail-on severity.
"""

import argparse
import os
import sys

from . import report, scan, store


def _cmd_scan(args):
    profile = scan.load_profile(args.profile)
    if args.fail_on:
        profile["fail_on"] = args.fail_on
    summary = scan.run_scan(profile, provider=args.provider, model=args.model)

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
    return summary["exit_code"]


def _print_summary(summary, out):
    print(f"\ntarget: {summary['target']}   risk: {summary['risk']}/100   "
          f"gate: {'PASS' if summary['passed'] else 'FAIL'} (fail-on {summary['fail_on']})")
    print(f"{'objective':<22}{'strategy':<14}{'result':<9}{'queries':<8}pruned")
    print("-" * 62)
    for r in summary["results"]:
        res = "BROKEN" if r.success else "held"
        print(f"{r.objective:<22}{r.strategy:<14}{res:<9}{r.queries:<8}{r.pruned}")
    print("-" * 62)
    if summary["findings"]:
        print(f"{len(summary['findings'])} finding(s):")
        for f in summary["findings"]:
            print(f"  [{f.severity}] {f.objective} - broken by {f.strategy} "
                  f"in {f.queries} queries ({f.atlas})")
    print(f"\nreports written to {out}/ (report.html, report.json, report.md)")


def main(argv=None):
    p = argparse.ArgumentParser(prog="redforge")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan", help="run a red-team scan")
    s.add_argument("--profile", default="profiles/default.json")
    s.add_argument("--out", default="results")
    s.add_argument("--provider", choices=["mock", "ollama", "openai", "anthropic"])
    s.add_argument("--model")
    s.add_argument("--fail-on", choices=["low", "medium", "high", "critical"])
    s.add_argument("--db", default="redforge.db", help="SQLite path; empty to skip")
    s.set_defaults(func=_cmd_scan)
    args = p.parse_args(argv)
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
