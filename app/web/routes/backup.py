"""Backup and restore route handlers.

Confidentiality model. Format 3 encrypts every payload member, including the
SQLite snapshot and activity log, using streaming authenticated encryption.
What the archive does NOT hide is metadata: the
manifest, the file names and the directory structure are stored in clear. A
portable backup adds ``master_key.wrapped`` — the master key sealed with the
operator's password (PBKDF2 + AES-GCM) — so the payload can be decrypted on
another machine by whoever knows that password. We therefore promise
portability and payload confidentiality, not metadata confidentiality; the
manifest is authenticated (HMAC under the master key) for integrity, not
secrecy. Whole-archive authenticated encryption would be needed to hide the
metadata too, and is deliberately not attempted here.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import shutil
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.core.exceptions import (
    AuthError,
    ConflictError,
    IntegrationError,
    NotFoundError,
    ValidationError,
)
from app.models.backup import BackupCreate, BackupRestore
from app.models.user import Role, User

# Serialize backup creation: a scheduled and a manual backup that overlap would
# write two archives into the same directory at once and, worse, each read a
# database mid-write by the other (SR-003 criterion 3).
from app.services.backups import _BACKUP_LOCK
from app.web.i18n import refusal, ui_t
from app.web.middleware.auth import require_role

router = APIRouter()
logger = logging.getLogger(__name__)

_admin = Depends(require_role(Role.admin))

# Serialize whole restores. _restore_in_progress is a single process-global; two
# overlapping restores would let the first's exit_restore_mode() lift the quiesce
# while the second is still swapping files. One restore at a time keeps the flag
# lifecycle unambiguous (SR-003 review). Bound lazily to the running loop.
_RESTORE_LOCK = asyncio.Lock()

# Archive-extraction limits, checked before anything is read out (SR-003 #6).
_MAX_ENTRIES = 500_000
_MAX_ENTRY_BYTES = 4 * 1024**3  # 4 GiB for the largest single file (the DB)
_MAX_TOTAL_BYTES = 50 * 1024**3  # 50 GiB uncompressed in total
# Per-entry ratio ceiling, above DEFLATE's ~1032:1 single-stream maximum. The
# DB snapshot is a plaintext SQLite file whose free/zeroed pages compress far
# past 500:1, so a tighter ceiling would reject a backup we just made (SR-003
# review). The absolute byte caps above — re-checked while streaming in
# _extract_entry — are the real defence against a decompression bomb; this only
# catches a header that *declares* a physically impossible ratio.
_MAX_COMPRESSION_RATIO = 1100
_CHUNK = 1 << 20
# Control members are read whole into memory, so they get their own tight caps
# (the 4 GiB entry cap above is far too loose for a manifest or a wrapped key).
_MAX_MANIFEST_BYTES = 128 * 1024**2  # a manifest of every archived file
_MAX_CONTROL_BYTES = 1 * 1024**2  # manifest.mac / master_key.wrapped are tiny


def _get_default_backup_dir() -> Path:
    from platformdirs import user_documents_dir

    return Path(user_documents_dir()) / "MSPToolkit" / "Backups"


def _master_key_fingerprint() -> str:
    """Return a SHA-256 hash of the master key (NOT the key itself)."""
    from app.core.encryption import _get_or_create_master_key

    return hashlib.sha256(_get_or_create_master_key()).hexdigest()


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _remove(path: Path) -> None:
    # Best-effort: cleanup of temp/rollback siblings must never raise, or a
    # failed unlink (EACCES/EIO, a lingering handle) would turn a successful
    # restore's tidy-up into a spurious rollback (SR-003 review).
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Could not remove %s: %s", path, e)


# ── Create ───────────────────────────────────────────────────────────────────


def create_backup_sync(dest_path: str | None = None, backup_password: str | None = None) -> dict:
    """Compatibility entrypoint; the backup engine is transport-independent."""
    from app.services.backups import create_backup_sync as create

    return create(dest_path or str(_get_default_backup_dir()), backup_password)


@router.post("/backup/create")
async def create_backup(request: Request, body: BackupCreate | None = None, user: User = _admin):
    """Create a full backup ZIP of all customer data.

    Optional JSON body: ``dest_path`` (output directory) and
    ``backup_password`` (wraps the master key into the archive for a portable,
    restore-anywhere backup).
    """
    body = body or BackupCreate()
    dest = body.dest_path.strip() or None
    backup_password = body.backup_password.strip() or None

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(None, lambda: create_backup_sync(dest, backup_password))
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    except Exception as e:
        raise IntegrationError(f"{ui_t('err_backup_failed', request)}: {e}") from e
    from app.core.activity_log import log_activity

    _user = getattr(getattr(request.state, "user", None), "username", "")
    log_activity("backup_created", detail=result["path"], user=_user)
    return result


# ── Restore ───────────────────────────────────────────────────────────────────


def _enforce_archive_limits(zf: zipfile.ZipFile) -> None:
    """Refuse a decompression bomb before a single byte is extracted (SR-003 #6)."""
    infos = zf.infolist()
    if len(infos) > _MAX_ENTRIES:
        raise refusal(ValidationError, "err_backup_too_many_files")
    total = 0
    for info in infos:
        if info.file_size > _MAX_ENTRY_BYTES:
            raise refusal(ValidationError, "err_backup_file_too_large", file=info.filename)
        total += info.file_size
        if total > _MAX_TOTAL_BYTES:
            raise refusal(ValidationError, "err_backup_too_large")
        if info.compress_size > 0 and info.file_size / info.compress_size > _MAX_COMPRESSION_RATIO:
            raise refusal(ValidationError, "err_backup_compression_ratio", file=info.filename)


def _extract_entry(zf: zipfile.ZipFile, entry: str, staging: Path) -> None:
    """Extract one entry under *staging*, guarding traversal and re-checking size."""
    target = (staging / entry).resolve()
    staging_r = staging.resolve()
    if target != staging_r and staging_r not in target.parents:
        raise refusal(ValidationError, "err_backup_path_traversal", path=entry)
    target.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with zf.open(entry) as src, target.open("wb") as dst:
        while True:
            chunk = src.read(_CHUNK)
            if not chunk:
                break
            written += len(chunk)
            if written > _MAX_ENTRY_BYTES:
                raise refusal(ValidationError, "err_backup_entry_over_limit", file=entry)
            dst.write(chunk)


def _stage_restore(zip_path: Path, backup_password: str | None) -> dict:
    """Open, validate and stage a restore into a temp dir — no live mutation.

    Everything that can fail — a wrong password, a corrupt archive, a mismatched
    hash, a broken database — is caught here, before any live data is touched
    (SR-003 #7). Returns the staging directory and what was found.
    """
    import base64 as _b64
    import tempfile

    from app.core.encryption import manifest_mac, unwrap_master_key_to_bytes

    def _read_bounded(zf: zipfile.ZipFile, name: str, cap: int) -> bytes:
        # Read a control member into memory only after checking its declared
        # size, so a lying header cannot force a huge allocation (SR-003 review).
        if zf.getinfo(name).file_size > cap:
            raise refusal(ValidationError, "err_backup_entry_unreasonable", name=name)
        return zf.read(name)

    staging = Path(tempfile.mkdtemp(prefix="sybr-restore-"))
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = set(zf.namelist())
            if "manifest.json" not in names:
                raise refusal(ValidationError, "err_backup_manifest_missing")
            _enforce_archive_limits(zf)

            manifest_bytes = _read_bounded(zf, "manifest.json", _MAX_MANIFEST_BYTES)
            manifest = json.loads(manifest_bytes)

            # SR-003 review (HIGH — downgrade): only an authenticated, format-2
            # backup is restorable. A missing MAC or older format is refused, not
            # silently trusted — otherwise stripping manifest.mac would skip the
            # integrity check and let an edited manifest through.
            if manifest.get("format") not in (2, 3) or "manifest.mac" not in names:
                raise refusal(ValidationError, "err_backup_unauthenticated")
            files = manifest.get("files")
            if not isinstance(files, dict) or not files:
                raise refusal(ValidationError, "err_backup_manifest_no_files")

            new_key_bytes: bytes | None = None
            new_key_b64: str | None = None
            # For a local (non-portable) backup the MAC below is verified under
            # the CURRENT master key, so reaching that check at all means the key
            # matches. There is no longer a "restore anyway under a mismatched
            # key" path — a backup we cannot authenticate is refused, not
            # restored with a warning (SR-003 review). key_match stays in the
            # result for API compatibility and is always True once we return.
            key_match = True
            if "master_key.wrapped" in names:
                if not backup_password:
                    raise refusal(ValidationError, "err_backup_password_required")
                wrapped = _read_bounded(zf, "master_key.wrapped", _MAX_CONTROL_BYTES).decode(
                    "utf-8"
                )
                new_key_bytes = unwrap_master_key_to_bytes(wrapped, backup_password)
                if new_key_bytes is None:
                    raise refusal(ValidationError, "err_backup_wrong_password")
                new_key_b64 = _b64.urlsafe_b64encode(new_key_bytes).decode()

            # SR-003 #4: authenticate the manifest under the key that owns this
            # backup (the one from the archive, else the current one). This is now
            # mandatory — after it passes, manifest["files"] is trusted, so it
            # (not the raw namelist) drives extraction below.
            expected = _read_bounded(zf, "manifest.mac", _MAX_CONTROL_BYTES).decode("utf-8").strip()
            got = manifest_mac(manifest_bytes, key=new_key_bytes)
            if not hmac.compare_digest(got, expected):
                raise refusal(ValidationError, "err_backup_signature_mismatch")

            # SR-003 review (HIGH — smuggled files): extract ONLY the files the
            # authenticated manifest lists. A file present in the zip but absent
            # from manifest.files is never written to staging, so it can never be
            # committed into config/, certs/ or anywhere else.
            total = 0
            for arc, meta in files.items():
                if arc not in names:
                    raise refusal(ValidationError, "err_backup_missing_file", file=arc)
                total += int(meta.get("size", 0) or 0)
                if total > _MAX_TOTAL_BYTES:
                    raise refusal(ValidationError, "err_backup_too_large")
                _extract_entry(zf, arc, staging)

        # Verify each staged file against the authenticated manifest (SR-003 #7).
        for arc, meta in files.items():
            staged = staging / arc
            if not staged.exists():
                raise refusal(ValidationError, "err_backup_missing_file", file=arc)
            if _hash_file(staged) != meta.get("sha256"):
                raise refusal(ValidationError, "err_backup_file_corrupt", file=arc)

        if manifest["format"] == 3:
            from app.core.backup_crypto import decrypt_member
            from app.core.encryption import _get_or_create_master_key

            archive_key = new_key_bytes or _get_or_create_master_key()
            for arc, meta in files.items():
                if meta.get("encoding") != "aes-gcm-v1":
                    raise refusal(ValidationError, "err_backup_unknown_cipher")
                try:
                    decrypt_member(staging / arc, archive_key, arc)
                except Exception as exc:
                    raise refusal(ValidationError, "err_backup_decrypt_failed") from exc

        staged_db = staging / "database" / "msp_toolkit.db"
        if staged_db.exists():
            import sqlite3

            con = sqlite3.connect(str(staged_db))
            try:
                row = con.execute("PRAGMA integrity_check").fetchone()
            finally:
                con.close()
            if not row or row[0] != "ok":
                raise refusal(ValidationError, "err_backup_db_integrity", result=row)
    except Exception:
        _remove(staging)
        raise

    return {
        "staging": staging,
        "manifest": manifest,
        "new_key_b64": new_key_b64,
        "key_match": key_match,
    }


def _commit_restore(staged: dict) -> dict:
    """Swap staged data into place, rolling back on any failure (SR-003 #8/#9).

    The database pool must already be closed by the caller. Every data class the
    backup touches is moved aside before its replacement lands; if anything
    fails partway, the moved-aside originals are put back, so a failed restore
    leaves the install exactly as it was.

    Each move-aside goes to a *sibling* of the live path, not a system temp dir:
    a sibling is always on the same filesystem, so the move is an atomic rename
    that either fully succeeds or leaves the original untouched — never a
    half-copied original that a later cleanup then destroys (SR-003 review).

    Residual, accepted: a restore *replaces* live data, so a connection that a
    concurrent request checked out before the quiesce may still write to the
    old, about-to-be-replaced database and lose that write. That is the intended
    meaning of a restore, not a corruption — the swapped-in file is always whole.
    """
    import os

    from app.core.config import CONFIG_DIR, DATA_DIR, get_audit_dir, get_cert_dir
    from app.core.encryption import import_master_key

    staging: Path = staged["staging"]
    db_path = DATA_DIR / "msp_toolkit.db"
    token = os.urandom(4).hex()
    targets = [
        (DATA_DIR / "customers", staging / "customers", "customers"),
        (DATA_DIR / "retired_customers", staging / "retired_customers", "retired_customers"),
        (get_audit_dir(), staging / "audits", "audits"),
        (CONFIG_DIR, staging / "config", "config"),
        (get_cert_dir(), staging / "certs", "certs"),
        (db_path, staging / "database" / "msp_toolkit.db", "database"),
        (DATA_DIR / "activity_log.jsonl", staging / "activity_log.jsonl", "activity_log"),
    ]

    # Every class we commit, so rollback restores originals AND removes classes
    # that did not exist before (bak is None for those) — the old code only
    # tracked classes that already existed, so a newly created one stuck around
    # after a failed restore (SR-003 review, MEDIUM).
    committed: list[tuple[Path, Path | None]] = []
    restored = {
        "customers": 0,
        "audits": 0,
        "config": 0,
        "certs": 0,
        "database": False,
        "activity_log": False,
    }

    # Serialize against create_backup_sync so a restore and a scheduled backup
    # cannot move the same trees at once (SR-003 review, MEDIUM). This also keeps
    # the sibling rollback files below invisible to add_tree, which only runs
    # under this same lock.
    with _BACKUP_LOCK:
        try:
            for live, src, key in targets:
                if not src.exists():
                    continue
                if live.exists():
                    bak = live.with_name(f".sybr-rollback-{token}-{live.name}")
                    shutil.move(str(live), str(bak))  # same-fs atomic rename
                    committed.append((live, bak))
                else:
                    committed.append((live, None))
                live.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(live))
                if key in ("database", "activity_log"):
                    restored[key] = True
                else:
                    restored[key] = sum(1 for p in live.rglob("*") if p.is_file())

            # Drop the stale WAL/SHM left beside the DB by the connections the
            # caller just closed: they belong to the *old* database and would
            # corrupt the freshly swapped-in one if SQLite tried to replay them.
            # Do this BEFORE adopting the key, so key adoption — the one step
            # with irreversible, un-rolled-back side effects (it rewrites the
            # on-disk key backups) — is the very last fallible action. A failure
            # anywhere above rolls the data back with the original key intact
            # (SR-003 review, HIGH — key/data mismatch).
            for sidecar in ("-wal", "-shm"):
                wal = db_path.with_name(db_path.name + sidecar)
                if wal.exists():
                    wal.unlink()

            # Adopt the backup's master key last. import_master_key only returns
            # False for malformed input (before it mutates anything), and the key
            # here already round-tripped through unwrap, so reaching this point
            # means it succeeds; nothing fallible runs after it.
            if staged["new_key_b64"] and not import_master_key(staged["new_key_b64"]):
                raise refusal(IntegrationError, "err_backup_key_adopt_failed")
        except Exception:
            # Undo every committed class, newest first: remove what we put in
            # place, then restore the moved-aside original if there was one.
            for live, bak in reversed(committed):
                _remove(live)
                if bak is not None:
                    shutil.move(str(bak), str(live))
            raise
        else:
            # Success — and only now, outside the rollback guard, drop the
            # move-aside originals. import_master_key above is thus the last
            # action that can trigger a rollback; a failure to tidy up a bak
            # here leaves the fully-consistent restore in place, never a
            # data-rolled-back-but-key-adopted mix (SR-003 review, MEDIUM).
            for _live, bak in committed:
                if bak is not None:
                    _remove(bak)
        finally:
            _remove(staging)

    return restored


@router.post("/backup/restore")
async def restore_backup(body: BackupRestore, request: Request, user: User = _admin):
    """Restore a backup from a ZIP file.

    Validates and stages the whole archive first; only once it is proven
    complete and consistent does it quiesce the database and swap the data in,
    with rollback if the swap fails (SR-003).

    JSON body: ``zip_path`` (path to the backup) and ``backup_password``
    (required when the backup carries a wrapped master key).
    """
    from app.core.database import close_pool, enter_restore_mode, exit_restore_mode

    zip_path_str = body.zip_path.strip()
    backup_password = body.backup_password.strip() or None
    if not zip_path_str:
        raise ValidationError(ui_t("err_no_file_path", request))

    zip_path = Path(zip_path_str).resolve()
    _safe_parents = [_get_default_backup_dir().resolve(), Path.home().resolve()]
    # Path-component containment, not a string prefix: /home/frank2 must not be
    # accepted just because it shares a prefix with /home/frank (SR-003 review).
    if not any(zip_path == p or p in zip_path.parents for p in _safe_parents):
        raise refusal(ValidationError, "err_backup_file_location")
    if not zip_path.exists() or not zip_path.is_file():
        raise NotFoundError(ui_t("err_file_not_found", request))
    if zip_path.suffix.lower() != ".zip":
        raise ValidationError(ui_t("err_file_must_be_zip", request))

    loop = asyncio.get_event_loop()
    staged = None
    async with _RESTORE_LOCK:  # one restore at a time (SR-003 review)
        try:
            # Phase 1: validate + stage. No live data is touched.
            staged = await loop.run_in_executor(
                None, lambda: _stage_restore(zip_path, backup_password)
            )
            # Phases 2+3 under a SCOPED quiesce. enter_restore_mode() makes any
            # new get_db() raise, so a concurrent request cannot lazily rebuild
            # the pool that close_pool() tears down while the files are being
            # swapped. The finally always lifts it: whether the commit succeeds
            # (new DB in place) or fully rolls back (original DB restored), the
            # file at DB_PATH is a complete database, so a rolled-back restore
            # must not leave the app bricked until a restart (SR-003 review).
            enter_restore_mode()
            try:
                await close_pool()
                restored = await loop.run_in_executor(None, lambda: _commit_restore(staged))
            finally:
                exit_restore_mode()
        except (ValidationError, NotFoundError, AuthError, ConflictError, IntegrationError):
            raise
        except Exception as e:
            raise IntegrationError(f"{ui_t('err_restore_failed', request)}: {e}") from e
        finally:
            # Reclaim the staging dir on EVERY exit — including CancelledError,
            # which is a BaseException the except clauses above do not catch —
            # unless _commit_restore already removed it (SR-003 review, LOW).
            if staged is not None:
                _remove(staged["staging"])

    from app.core.activity_log import log_activity

    _user = getattr(getattr(request.state, "user", None), "username", "")
    log_activity("backup_restored", detail=zip_path_str, user=_user)

    return {
        "ok": True,
        "key_match": staged["key_match"],  # always True once we reach here
        "manifest": staged["manifest"],
        "restored_files": restored,
        "restart_required": restored.get("database", False),
    }


@router.get("/backup/info")
async def backup_info(user: User = _admin):
    """Return last backup date and default backup dir."""
    from app.core.config import load_app_settings

    settings = load_app_settings()
    return {
        "last_backup_date": settings.get("last_backup_date", ""),
        "last_backup_path": settings.get("last_backup_path", ""),
        "default_backup_dir": str(_get_default_backup_dir()),
    }
