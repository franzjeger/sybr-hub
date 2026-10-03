"""Request models for the backup endpoints."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class BackupCreate(BaseModel):
    """Optional: where to write the archive, and a password to wrap the master
    key into it for a restore-anywhere backup. Empty means the default and no
    wrapped key."""

    model_config = ConfigDict(extra="forbid")

    dest_path: str = ""
    backup_password: str = ""


class BackupRestore(BaseModel):
    """The archive to restore, and its password when it carries a wrapped key.

    A missing path keeps the handler's translated message.
    """

    model_config = ConfigDict(extra="forbid")

    zip_path: str = ""
    backup_password: str = ""
