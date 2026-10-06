from __future__ import annotations

import os
import tempfile
from pathlib import Path


def ensure_private_directory(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    resolved.chmod(0o700)
    return resolved


def write_private_bytes(path: Path, content: bytes) -> Path:
    destination = path.expanduser().resolve()
    directory = ensure_private_directory(destination.parent)
    file_descriptor, temporary_name = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        temporary.replace(destination)
        destination.chmod(0o600)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def write_private_text(path: Path, content: str) -> Path:
    return write_private_bytes(path, content.encode("utf-8"))
