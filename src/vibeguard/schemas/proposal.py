"""Patch proposal schema."""

from pydantic import BaseModel


class PatchProposal(BaseModel):
    patch: str
    files: list[str]
    reason: str
    risk: str = "low"
