"""
RescueNet Offline File & Attachment Storage Manager.

Provides content-addressable storage for offline situational photos, casualty cards,
and map diagrams shared across laptops over local Wi-Fi without internet.
"""

from __future__ import annotations
import base64
import hashlib
import mimetypes
import os
import re
from typing import Dict, Any, Optional, Tuple, List


DEFAULT_ATTACHMENTS_DIR = os.path.join("data", "attachments")
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024  # 5 MB max per offline file


def sanitize_filename(filename: str) -> str:
    """Sanitize filename to prevent directory traversal or invalid characters."""
    clean = os.path.basename(filename)
    clean = re.sub(r'[^a-zA-Z0-9_.-]', '_', clean)
    return clean or "attachment.bin"


class AttachmentManager:
    """
    Manages local storage and verification of attachments transferred over the offline mesh.
    """

    def __init__(self, base_dir: str = DEFAULT_ATTACHMENTS_DIR) -> None:
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)

    def save_file(
        self,
        filename: str,
        content: bytes,
        description: str = "",
        uploader: str = "",
    ) -> Dict[str, Any]:
        """
        Store a new file locally, compute its SHA-256 hash, and return attachment metadata
        with embedded base64 representation for mesh synchronization.
        """
        if len(content) > MAX_ATTACHMENT_BYTES:
            raise ValueError(f"File size {len(content)} exceeds maximum limit {MAX_ATTACHMENT_BYTES} bytes")

        sha256 = hashlib.sha256(content).hexdigest()
        file_id = sha256[:16]
        safe_name = sanitize_filename(filename)
        dest_filename = f"{sha256[:12]}_{safe_name}"
        dest_path = os.path.join(self.base_dir, dest_filename)

        with open(dest_path, "wb") as f:
            f.write(content)

        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            mime_type = "application/octet-stream"

        data_b64 = base64.b64encode(content).decode("ascii")

        return {
            "file_id": file_id,
            "filename": safe_name,
            "file_size": len(content),
            "sha256": sha256,
            "mime_type": mime_type,
            "description": description,
            "uploader": uploader,
            "data_base64": data_b64,
            "stored_filename": dest_filename,
        }

    def ingest_attachment_event(self, payload: Dict[str, Any]) -> Optional[str]:
        """
        Ingest an attachment payload received from a peer during sync.
        Decodes base64 payload, verifies SHA-256 hash, and saves file to local disk.
        """
        sha256 = payload.get("sha256")
        data_b64 = payload.get("data_base64")
        filename = payload.get("filename", "mesh_attachment.bin")

        if not sha256 or not data_b64:
            return None

        safe_name = sanitize_filename(filename)
        dest_filename = f"{sha256[:12]}_{safe_name}"
        dest_path = os.path.join(self.base_dir, dest_filename)

        # Idempotent: If file already exists with same size, skip writing
        if os.path.exists(dest_path):
            return dest_path

        try:
            content = base64.b64decode(data_b64)
            computed = hashlib.sha256(content).hexdigest()
            if computed != sha256:
                return None  # Corrupted or tampered file

            with open(dest_path, "wb") as f:
                f.write(content)

            return dest_path
        except Exception:
            return None

    def get_attachment(self, file_id: str) -> Optional[Tuple[str, str, str]]:
        """
        Lookup attachment by file_id (or prefix) and return (filepath, filename, mime_type).
        """
        for fname in os.listdir(self.base_dir):
            if fname.startswith(file_id[:12]):
                fpath = os.path.join(self.base_dir, fname)
                orig_name = fname.split("_", 1)[1] if "_" in fname else fname
                mime_type, _ = mimetypes.guess_type(orig_name)
                return (fpath, orig_name, mime_type or "application/octet-stream")
        return None

    def list_attachments(self) -> List[Dict[str, Any]]:
        """List all stored attachments on this node."""
        results = []
        for fname in os.listdir(self.base_dir):
            fpath = os.path.join(self.base_dir, fname)
            if os.path.isfile(fpath):
                stat = os.stat(fpath)
                parts = fname.split("_", 1)
                file_id = parts[0]
                orig_name = parts[1] if len(parts) > 1 else fname
                mime_type, _ = mimetypes.guess_type(orig_name)
                results.append({
                    "file_id": file_id,
                    "filename": orig_name,
                    "file_size": stat.st_size,
                    "modified_at": stat.st_mtime,
                    "mime_type": mime_type or "application/octet-stream",
                    "path": fpath,
                })
        return sorted(results, key=lambda x: x["modified_at"], reverse=True)
