"""Host-injected GitHub MCP shipment contract.

VibeGuard deliberately does not accept or persist GitHub tokens. The TrueForge host calls
its connected GitHub MCP after shipment approval, then records the resulting PR on the run.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ShipmentRequest:
    repository: str
    base_branch: str
    branch: str
    commit_message: str
    files: dict[str, str]
    pull_request_title: str
    pull_request_body: str


@dataclass(frozen=True)
class ShipmentResult:
    branch: str
    commit_sha: str
    pull_request_url: str


class GitHubShipmentProvider(Protocol):
    def ship(self, request: ShipmentRequest) -> ShipmentResult: ...
