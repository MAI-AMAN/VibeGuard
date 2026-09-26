"""VibeGuard command-line interface."""

import argparse
import sys
from pathlib import Path

from vibeguard.audit.events import RunStore
from vibeguard.schemas.run import AuditRun
from vibeguard.workflow.orchestrator import ApprovalRequired, Orchestrator
from vibeguard.workflow.services import ReliabilityAnalyzer, RepositoryObserver

BANNER = """╭─────────────────────────────────────────────╮
│ VIBEGUARD                                   │
│ Your vibe code. We make it ship.            │
╰─────────────────────────────────────────────╯"""


def print_run(run: AuditRun) -> None:
    print(
        f"\nRun ID: {run.run_id}\nState:  {run.state.value}\nRepository: {run.repository}"
    )
    if run.finding:
        print("\nFinding")
        print(f"  {run.finding.severity} / {run.finding.confidence} confidence")
        print(f"  {run.finding.file}:{run.finding.line or '?'}")
        print(f"  {run.finding.description}")
    if run.reproduction:
        mark = "✓" if run.reproduction.status == "REPRODUCED" else "!"
        print(f"\nReproduction: {mark} {run.reproduction.status}")
        print(
            f"  exit={run.reproduction.execution.exit_code} "
            f"duration={run.reproduction.execution.duration_ms}ms"
        )
        print(f"  {run.reproduction.observed}")
    if run.patch:
        print("\nPatch review")
        print(run.patch)
    if run.verification:
        print(
            f"\nVerification: {'✓ PASSED' if run.verification.passed else '✗ FAILED'}"
        )
        for check in run.verification.checks:
            print(f"  {'✓' if check.exit_code == 0 else '✗'} {' '.join(check.command)}")
    if run.state.value.startswith("WAITING_FOR_"):
        print("\n! Human approval required. No consequential action was performed.")


def repository(value: str) -> Path:
    path = Path(value).resolve()
    if not (path / ".git").exists():
        raise argparse.ArgumentTypeError(f"Not a Git repository: {path}")
    return path


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="vibeguard", description="Human-gated reliability agent"
    )
    root.add_argument(
        "--repo", type=repository, default=Path.cwd(), help="repository path"
    )
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "audit", help="observe through reproduction, then pause for approval"
    )
    commands.add_parser("analyze", help="show static reliability findings")
    commands.add_parser("investigate", help="alias for audit")
    commands.add_parser("reproduce", help="show the latest reproduction")
    commands.add_parser("status", help="show the latest or selected run").add_argument(
        "--run"
    )
    fix = commands.add_parser("fix", help="approve remediation and generate a patch")
    fix.add_argument("--run", required=True)
    fix.add_argument("--approve", action="store_true")
    verify = commands.add_parser("verify", help="approve patch and verify it")
    verify.add_argument("--run", required=True)
    verify.add_argument("--approve", action="store_true")
    ship = commands.add_parser("ship", help="approve verified shipment")
    ship.add_argument("--run", required=True)
    ship.add_argument("--approve", action="store_true")
    return root


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    repo = args.repo.resolve()
    flow = Orchestrator(repo)
    print(BANNER)
    try:
        if args.command in {"audit", "investigate"}:
            print("\n[1/5] OBSERVE → [2/5] ANALYZE → [3/5] EVIDENCE → [4/5] REPRODUCE")
            print_run(flow.audit())
        elif args.command == "analyze":
            profile = RepositoryObserver().observe(repo)
            print(f"\n{profile.name} · {profile.language} · {profile.branch}")
            findings = ReliabilityAnalyzer.analyze(repo)
            for finding in findings:
                print(
                    f"{finding.severity} {finding.file}:{finding.line} — {finding.description}"
                )
            if not findings:
                print("✓ No actionable finding detected")
        elif args.command in {"status", "reproduce"}:
            store = RunStore(repo)
            run = store.load(args.run) if getattr(args, "run", None) else store.latest()
            if run is None:
                print("\nNo VibeGuard runs found.")
            else:
                print_run(run)
        elif args.command == "fix":
            print_run(flow.generate_patch(args.run, args.approve))
        elif args.command == "verify":
            print_run(flow.verify(args.run, args.approve))
        elif args.command == "ship":
            print_run(flow.ship(args.run, args.approve))
    except (ApprovalRequired, ValueError, FileNotFoundError, RuntimeError) as error:
        print(f"\n✗ {error}", file=sys.stderr)
        raise SystemExit(2) from error
