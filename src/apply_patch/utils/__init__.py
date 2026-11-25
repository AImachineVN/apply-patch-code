from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

PathLike = str | Path

__all__ = ["PathLike", "sha256_file", "write_bytes_atomic", "write_text_atomic"]


def sha256_file(path: PathLike, chunk_size: int = 65536) -> str:
    """
    Tính băm SHA-256 của một file.
    Đọc theo từng chunk (mặc định 64KB) để tiết kiệm bộ nhớ khi băm file lớn.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Cannot hash non-existent file: {path}")
        
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_text_atomic(path: PathLike, content: str, encoding: str = "utf-8") -> None:
    """
    Ghi nội dung text vào file một cách an toàn (atomic).
    newline="" được dùng để bảo toàn CRLF/LF trên Windows.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_bytes_atomic(path: PathLike, content: bytes) -> None:
    """
    Ghi nội dung bytes vào file một cách an toàn (atomic).
    Dùng cho việc ghi file backup nhị phân hoặc dữ liệu thô.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise