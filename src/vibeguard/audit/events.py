"""Persistent run store and structured event journal."""

import json
from pathlib import Path
from typing import Any

from vibeguard.schemas.run import AuditRun, RunEvent, now_iso
from vibeguard.workflow.states import State, transition


class RunStore:
    def __init__(self, repository: Path) -> None:
        self.root = repository / ".vibeguard" / "runs"

    def create(self, repository: str) -> AuditRun:
        run = AuditRun(repository=repository)
        self.save(run)
        self.emit(run, "run.created", "Audit run created")
        return run

    def save(self, run: AuditRun) -> None:
        run.updated_at = now_iso()
        directory = self.root / run.run_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "state.json").write_text(run.model_dump_json(indent=2) + "\n")

    def load(self, run_id: str) -> AuditRun:
        path = self.root / run_id / "state.json"
        if not path.exists():
            raise FileNotFoundError(f"Unknown VibeGuard run: {run_id}")
        return AuditRun.model_validate_json(path.read_text())

    def latest(self) -> AuditRun | None:
        states = sorted(
            self.root.glob("*/state.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return AuditRun.model_validate_json(states[0].read_text()) if states else None

    def move(self, run: AuditRun, target: State, message: str, **data: Any) -> None:
        run.state = transition(run.state, target)
        self.save(run)
        self.emit(run, "state.transition", message, data)

    def emit(
        self,
        run: AuditRun,
        event: str,
        message: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        item = RunEvent(
            event=event,
            run_id=run.run_id,
            state=run.state,
            message=message,
            data=data or {},
        )
        directory = self.root / run.run_id
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / "events.jsonl").open("a") as stream:
            stream.write(
                json.dumps(item.model_dump(mode="json"), sort_keys=True) + "\n"
            )
