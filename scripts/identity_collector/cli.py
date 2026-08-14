"""CLI dispatch for the 5 subcommands (prereg API Contracts). All mutating
commands accept --dry-run; diagnose-history/replay/health are always
read-only. Stage 1: primary_root/mirror_root remain PENDING (Stage 2 not
authorized), so `collect`/`qualify-month` fail closed here rather than
guessing a root -- this is correct Stage-1 behavior, not a bug.
"""
import argparse
import sys


class RootsNotConfigured(Exception):
    """Stage 2 (primary_root/mirror_root) is not authorized yet."""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="identity_collector.py")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("diagnose-history")
    d.add_argument("--config", required=True)

    c = sub.add_parser("collect")
    c.add_argument("--as-of", required=True)
    c.add_argument("--config", required=True)
    c.add_argument("--dry-run", action="store_true")

    q = sub.add_parser("qualify-month")
    q.add_argument("--month", required=True)
    q.add_argument("--config", required=True)
    q.add_argument("--dry-run", action="store_true")

    r = sub.add_parser("replay")
    r.add_argument("--run-id", required=True)
    r.add_argument("--offline", action="store_true")

    h = sub.add_parser("health")
    h.add_argument("--config", required=True)

    u = sub.add_parser("unlock")
    u.add_argument("--run-id", required=True)
    u.add_argument("--reason", required=True)

    return p


def run_collect_dry_run(as_of: str, mode: str = "balanced") -> dict:
    """Item 5 fix: --dry-run must work with real read-only source adapters
    even though primary_root/mirror_root remain PENDING -- it computes and
    reports, but writes nothing anywhere (no evidence root is touched, dry-run
    or not). Returns a summary dict rather than a full RunReceipt (dry-run is
    explicitly `projection_only`-flavored, not a committed evidence claim)."""
    from identity_collector import fusion
    from identity_collector.source_adapters import SourceReadError

    try:
        app_membership, l4a_membership, p_a, p_b = fusion.run_real_dual_fusion(as_of, mode=mode)
    except SourceReadError as e:
        return {"dry_run": True, "as_of": as_of, "mode": mode, "status": "MISSING_SOURCE", "detail": str(e)}
    except fusion.ProductionInternalDivergence as e:
        return {"dry_run": True, "as_of": as_of, "mode": mode, "status": "PRODUCTION_INTERNAL_DIVERGENCE", "detail": str(e)}
    except fusion.FrozenInputMutatedDuringComputation as e:
        return {"dry_run": True, "as_of": as_of, "mode": mode, "status": "SOURCE_MUTATED_MID_RUN", "detail": str(e)}
    return {
        "dry_run": True, "as_of": as_of, "mode": mode, "status": "OK",
        "p_a_rows": len(p_a), "p_b_rows": len(p_b), "fusion_membership_count": len(app_membership),
        "fusion_membership": sorted(app_membership),
    }


def dispatch(args: argparse.Namespace) -> int:
    if args.command == "diagnose-history":
        print("diagnose-history: read-only, see research/p0_r2_identity_collector/history_gap_report.md (already archived)")
        return 0
    if args.command == "collect":
        if args.dry_run:
            result = run_collect_dry_run(args.as_of)
            print(result)
            return 0
        raise RootsNotConfigured(
            "collect: primary_root/mirror_root are PENDING (Stage 2 not authorized) -- "
            "cannot write live evidence. Fails closed rather than guessing a root. Use --dry-run."
        )
    if args.command == "qualify-month":
        if args.dry_run:
            print(f"qualify-month --month {args.month} --dry-run: no evidence roots exist yet (Stage 1) -- nothing to qualify")
            return 0
        raise RootsNotConfigured(
            "qualify-month: primary_root/mirror_root are PENDING (Stage 2 not authorized) -- "
            "cannot write live evidence. Fails closed rather than guessing a root. Use --dry-run."
        )
    if args.command == "replay":
        print(f"replay --run-id {args.run_id} --offline: no evidence roots exist yet (Stage 1)")
        return 0
    if args.command == "health":
        print("health: no evidence roots exist yet (Stage 1) -- nothing to report")
        return 0
    if args.command == "unlock":
        print(f"unlock --run-id {args.run_id} --reason {args.reason!r}: no lock directory configured yet (Stage 1)")
        return 0
    raise ValueError(f"unknown command {args.command!r}")


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return dispatch(args)
    except RootsNotConfigured as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
