# VibeGuard

> **Your vibe code. We make it ship.**

VibeGuard is a human-gated software reliability agent for TrueForge. It turns a concrete
code risk into grounded evidence, a sandbox reproduction, a minimal patch, verified results,
and an approved GitHub pull request—without giving an autonomous process permission to make
consequential changes on its own.

## Problem

Fast-moving and AI-assisted code often passes the happy path while failing at real boundaries:
missing fields, swallowed exceptions, absent timeouts, unsafe retries, and weak validation.
A warning alone does not get that code safely to production.

## Solution

VibeGuard owns one reliability job end to end:

```text
OBSERVE → ANALYZE → EVIDENCE → REPRODUCE
                                  ↓
                         HUMAN APPROVAL #1
                                  ↓
                     GENERATE PATCH (not apply)
                                  ↓
                         HUMAN APPROVAL #2
                                  ↓
                    VERIFY IN ISOLATED WORKTREE
                                  ↓
                         HUMAN APPROVAL #3
                                  ↓
                    SHIP THROUGH GITHUB MCP
```

The explicit state machine persists every transition and fails closed on invalid transitions.

## Architecture

- **CLI and orchestrator** coordinate one complete audit.
- **Repository observer** reads real Git metadata, language, package manager, test framework,
  recent commits, and changed files.
- **AST analyzer** emits structured, source-grounded findings. Current high-confidence rules
  detect swallowed broad exceptions and direct indexing of unvalidated decoded JSON.
- **Evidence collector** correlates source lines, file-specific Git history, branch, and HEAD.
- **Reproduction engine** executes an allowlisted Python command with a timeout and captures
  stdout, stderr, exit code, and duration.
- **Patch engine** creates a unified diff and applies it only to an isolated run worktree after
  patch approval.
- **Verification engine** runs regression checks, pytest, Ruff, and mypy. Any failure blocks
  shipment.
- **Run store** writes `state.json` and append-only `events.jsonl` under
  `.vibeguard/runs/<run-id>/`.
- **Policy engine** classifies actions as `READ_ONLY`, `REQUIRES_APPROVAL`, or `FORBIDDEN` and
  rejects sensitive paths, scope drift, force pushes, merges, production deploys, deletion,
  and credential manipulation.

## TrueForge and MCPs

TrueForge supplies the isolated command-execution environment and the human-in-the-loop host.
The CLI deliberately does not read or persist GitHub tokens. After Gate 3, the host invokes the
connected **GitHub MCP** to create the branch, commit files, and open the pull request, then
records the real PR result on the run. If the MCP write action is unavailable, VibeGuard keeps
the verified patch ready and reports that no external change was made.

GitHub is the implemented shipment integration. Sentry, Linear, and DeepWiki are optional
future evidence providers; this version does not claim data from them.

## Three approval gates

1. **Remediation approval** — after evidence and reproduction, before patch generation.
2. **Patch approval** — after the exact diff is visible, before applying it to the isolated
   verification worktree.
3. **Shipment approval** — after all verification passes, before any GitHub write.

A missing approval is never interpreted as consent. Use of `--approve` represents an explicit
approval passed from the TrueForge human approval step; it is intentionally absent by default.

## Install

```bash
uv sync
uv run vibeguard --help
```

Python 3.11 or newer is required.

## CLI

```bash
vibeguard audit                         # runs through reproduction, then pauses
vibeguard analyze                       # source-grounded findings only
vibeguard investigate                   # audit alias
vibeguard reproduce                     # latest reproduction/status
vibeguard status [--run RUN_ID]
vibeguard fix --run RUN_ID --approve    # Gate 1 → generate patch, then pause
vibeguard verify --run RUN_ID --approve # Gate 2 → isolated verification, then pause
vibeguard ship --run RUN_ID --approve   # Gate 3 → hand off to GitHub MCP host
```

Use `--repo /path/to/repository` before the subcommand to target another local Git checkout.

## Demo

The repository includes `examples/demo_fragile.py`, an explicitly labelled deterministic demo
fixture. It contains a real missing-field failure; results are not mocked.

```bash
uv run vibeguard audit
# copy the printed run ID after reviewing evidence and reproduction
uv run vibeguard fix --run <RUN_ID> --approve
# review the exact diff
uv run vibeguard verify --run <RUN_ID> --approve
# review real test/lint/type results
uv run vibeguard ship --run <RUN_ID> --approve
```

At the final step, the TrueForge host performs the approved GitHub MCP branch/commit/PR calls.
The CLI itself never silently pushes or merges.

## Development

```bash
uv sync
uv run pytest -q
uv run ruff check .
uv run mypy src
uv build
```

Tests cover state transitions, all three gates, policy classifications, structured analysis,
real Git evidence, sandbox result handling, patch isolation, verification failure blocking, and
shipment gating.

## Security

- Generated commands are argument arrays, never shell strings.
- Only Python/pytest/Ruff/mypy executables are allowlisted for reliability execution.
- Commands have timeouts and cannot set a working directory outside the repository sandbox.
- Runtime artifacts and isolated worktrees are gitignored.
- Credentials are neither loaded nor logged by VibeGuard.
- Sensitive paths and destructive external actions are denied by policy.
- Merge and deployment are intentionally out of scope.

## AI assistance disclosure

AI coding assistance was used during development. The implementation was executed and validated
in the TrueForge sandbox; tests and command results in project reports are actual outputs rather
than generated claims.
