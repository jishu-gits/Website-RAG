# backend/app/services/storage.py
"""Simple storage backend for processed documents.

For now we store each document as a JSON file under ``data/processed_documents``.
The function returns a generated document ID (SHA‑256 of the URL) which can be
used later for embedding or retrieval.
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, Any

from app.core.logger import logger

STORAGE_DIR = Path(__file__).resolve().parents[2] / "data" / "processed_documents"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

async def store_document(doc: Dict[str, Any]) -> str:
    """Persist *doc* to disk and return its unique ID.

    The ID is a short hash of the document URL to guarantee uniqueness across
    crawls. The function is async to keep the API non‑blocking, but the
    implementation is synchronous because file I/O is fast for our prototype.
    """
    url = doc.get("url", "")
    doc_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    file_path = STORAGE_DIR / f"{doc_id}.json"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
        logger.info("Document stored", doc_id=doc_id, path=str(file_path))
    except Exception as exc:
        logger.error("Failed to store document", doc_id=doc_id, error=str(exc))
        raise
    return doc_id
