"""Pipeline-level exceptions with explicit stage names."""

from __future__ import annotations


class PipelineStageError(RuntimeError):
    """Base error enriched with the failing stage."""

    def __init__(self, stage: str, message: str):
        self.stage = stage
        super().__init__(f"[{stage}] {message}")


class HtmlCollectionError(PipelineStageError):
    """Raised when HTML collection fails."""


class ParsingError(PipelineStageError):
    """Raised when domain parsing fails."""


class PersistenceError(PipelineStageError):
    """Raised when database persistence fails."""


class ServingError(PipelineStageError):
    """Raised when UI serving stage fails."""
