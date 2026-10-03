"""Streaming AES-GCM for backup members, with bounded memory use.

Files are authenticated against their archive path. Decryption publishes no
plaintext until the final GCM tag is verified; callers use private staging.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b"SYBR-BACKUP-GCM-1\x00"
CHUNK = 1024 * 1024


def encrypt_member(source: Path, destination, key: bytes, archive_name: str) -> dict:
    nonce = os.urandom(12)
    header = MAGIC + nonce
    encryptor = Cipher(algorithms.AES(key), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(header + archive_name.encode("utf-8"))
    digest = hashlib.sha256()
    size = 0

    def write(data):
        nonlocal size
        destination.write(data)
        digest.update(data)
        size += len(data)

    write(header)
    # Open once: an atomic replacement by a writer cannot mix versions between
    # the archived bytes and the manifest hash.
    with source.open("rb") as stream:
        while chunk := stream.read(CHUNK):
            write(encryptor.update(chunk))
    write(encryptor.finalize())
    write(encryptor.tag)
    return {"size": size, "sha256": digest.hexdigest(), "encoding": "aes-gcm-v1"}


def decrypt_member(path: Path, key: bytes, archive_name: str) -> None:
    with path.open("rb") as source:
        header = source.read(len(MAGIC) + 12)
        if len(header) != len(MAGIC) + 12 or not header.startswith(MAGIC):
            raise ValueError("Invalid encrypted backup member")
        remaining = source.seek(0, 2) - len(header) - 16
        if remaining < 0:
            raise ValueError("Truncated encrypted backup member")
        source.seek(-16, 2)
        tag = source.read(16)
        source.seek(len(header))
        decryptor = Cipher(algorithms.AES(key), modes.GCM(header[-12:], tag)).decryptor()
        decryptor.authenticate_additional_data(header + archive_name.encode("utf-8"))
        descriptor, temporary = tempfile.mkstemp(prefix=".decrypt-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as target:
                while remaining:
                    chunk = source.read(min(CHUNK, remaining))
                    if not chunk:
                        raise ValueError("Truncated encrypted backup member")
                    remaining -= len(chunk)
                    target.write(decryptor.update(chunk))
                target.write(decryptor.finalize())
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
