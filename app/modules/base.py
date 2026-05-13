"""Base classes for all MSP Toolkit modules and audit sections."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Optional


class SectionStatus(Enum):
    PENDING  = auto()
    RUNNING  = auto()
    DONE     = auto()
    SKIPPED  = auto()
    FAILED   = auto()


@dataclass
class SectionResult:
    name:    str
    status:  SectionStatus = SectionStatus.PENDING
    files:   list[str]     = field(default_factory=list)
    warns:   list[str]     = field(default_factory=list)
    error:   Optional[str] = None

    @property
    def has_warnings(self) -> bool:
        return bool(self.warns)

    @property
    def status_icon(self) -> str:
        return {
            SectionStatus.PENDING:  "⏳",
            SectionStatus.RUNNING:  "⚡",
            SectionStatus.DONE:     "✓",
            SectionStatus.SKIPPED:  "→",
            SectionStatus.FAILED:   "✗",
        }[self.status]


# Callback type: called by sections to report progress
ProgressCallback = Callable[[str, SectionStatus, Optional[str]], None]


class BaseSection(ABC):
    """Base class for a single audit section."""

    name:        str = "Unknown Section"
    description: str = ""

    def __init__(self, out_dir: Path, progress_cb: Optional[ProgressCallback] = None):
        self.out_dir     = out_dir
        self.progress_cb = progress_cb
        self.result      = SectionResult(name=self.name)

    def _report(self, status: SectionStatus, detail: Optional[str] = None) -> None:
        self.result.status = status
        if self.progress_cb:
            self.progress_cb(self.name, status, detail)

    def _save(self, filename: str, content: str) -> None:
        from app.core.encryption import encrypted_write_text
        path = self.out_dir / filename
        encrypted_write_text(path, content)
        self.result.files.append(filename)

    def _warn(self, msg: str) -> None:
        self.result.warns.append(msg)

    @abstractmethod
    async def collect(self) -> SectionResult:
        """Run the section and return its result."""
        ...


class BaseModule(ABC):
    """Base class for top-level modules (M365 Audit, Fortigate, Unifi, ...)."""

    name:        str = "Unknown Module"
    description: str = ""
    icon:        str = "◆"
    available:   bool = True

    @abstractmethod
    async def run(self, **kwargs) -> None: ...
