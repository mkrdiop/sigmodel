"""Exceptions raised by the SIG data model."""

from __future__ import annotations


def join_path(base: str, part: str) -> str:
    """Join JSON-style path segments: ``nodes[3]`` + ``domain`` -> ``nodes[3].domain``."""
    if not base:
        return part
    if not part:
        return base
    if part.startswith("["):
        return base + part
    return f"{base}.{part}"


class SIGError(ValueError):
    """A SIG document or model object is malformed.

    ``path`` locates the problem inside the document (for example
    ``nodes[3].domain``) and is empty when the problem is not tied to a location.
    """

    def __init__(self, message: str, path: str = "") -> None:
        super().__init__(f"{path}: {message}" if path else message)
        self.message = message
        self.path = path

    def with_path(self, prefix: str) -> "SIGError":
        """Return a copy whose path is nested under ``prefix``."""
        return SIGError(self.message, join_path(prefix, self.path))
