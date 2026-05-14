"""MongoDB adapter for codebase chunk search (user-scoped text match + BM25 rank)."""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from rank_bm25 import BM25Okapi

from src.server.settings import settings

logger = logging.getLogger(__name__)

_client = None

# Whitespace-separated tokens; keeps CJK runs as single tokens when not split by spaces.
_TOKEN_RE = re.compile(r"[^\s]+")

_PROJECT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _bm25_max_candidates_clamped() -> int:
    n = int(settings.CODEBASE_MONGO_BM25_MAX_CANDIDATES)
    return max(1, min(n, 5000))


def validate_project_id(project_id: Optional[str]) -> str:
    """Return stripped project_id or raise ValueError if missing/invalid."""
    if project_id is None or not str(project_id).strip():
        raise ValueError("project_id is required for nested_user_doc layout")
    s = str(project_id).strip()
    if not _PROJECT_ID_RE.fullmatch(s):
        raise ValueError(
            "project_id must be non-empty and only contain letters, digits, underscore, hyphen"
        )
    return s


def tokenize(text: str) -> List[str]:
    """Lowercase, then split on whitespace into non-empty segments (query and docs use the same rule)."""
    if not text or not str(text).strip():
        return []
    return _TOKEN_RE.findall(str(text).lower())


def _get_client():
    """Lazy singleton Motor client. Lambda: connection pooling across warm invocations."""
    global _client
    if _client is None:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
        except ImportError as e:
            raise RuntimeError(
                "motor is required for codebase Mongo search; pip install motor"
            ) from e
        uri = settings.CODEBASE_MONGO_URI
        if not uri:
            raise RuntimeError("CODEBASE_MONGO_URI is not configured")
        _client = AsyncIOMotorClient(uri)
    return _client


def _bm25_rank_slice(
    rows: List[Dict[str, Any]],
    contents: List[str],
    query_tokens: List[str],
    stripped: str,
    top_k_clamped: int,
    preview_max: int,
) -> List[Dict[str, Any]]:
    """Sort rows by BM25 scores over contents; return top_k_clamped preview dicts."""
    if not rows:
        return []

    tokenized_corpus: List[List[str]] = [tokenize(c) for c in contents]
    if not query_tokens or not any(tokenized_corpus):
        order = range(min(len(rows), top_k_clamped))
        scores_list = [0.0] * len(rows)
    else:
        bm25 = BM25Okapi(tokenized_corpus)
        scores = bm25.get_scores(query_tokens)
        try:
            scores_list = [float(s) for s in scores]
        except TypeError:
            scores_list = [float(s) for s in list(scores)]
        order = sorted(
            range(len(rows)),
            key=lambda i: scores_list[i],
            reverse=True,
        )[:top_k_clamped]

    out: List[Dict[str, Any]] = []
    for i in order:
        r = rows[i]
        raw_content = r["_raw"]
        preview = raw_content[:preview_max]
        out.append(
            {
                "path": r["_path"],
                "content_preview": preview,
                "content_length": len(raw_content),
                "id": r["_id"],
                "bm25_score": scores_list[i],
            }
        )
    return out


async def _fetch_rows_flat(
    collection: Any,
    uid_field: str,
    path_field: str,
    content_field: str,
    user_id: int,
    escaped: str,
    fetch_limit: int,
) -> tuple[List[Dict[str, Any]], List[str]]:
    filt: Dict[str, Any] = {
        uid_field: user_id,
        content_field: {"$regex": escaped, "$options": "i"},
    }
    cursor = collection.find(
        filt,
        projection={path_field: 1, content_field: 1},
        limit=fetch_limit,
    )
    rows: List[Dict[str, Any]] = []
    contents: List[str] = []
    async for doc in cursor:
        raw_content = doc.get(content_field) or ""
        text = raw_content if isinstance(raw_content, str) else str(raw_content)
        path_val = doc.get(path_field, "")
        oid = doc.get("_id")
        rows.append(
            {
                "_path": str(path_val) if path_val is not None else "",
                "_raw": text,
                "_id": str(oid) if oid is not None else "",
            }
        )
        contents.append(text)
    return rows, contents


async def _fetch_rows_nested(
    collection: Any,
    uid_field: str,
    path_field: str,
    content_field: str,
    user_id: int,
    project_id: str,
    escaped: str,
    fetch_limit: int,
) -> tuple[List[Dict[str, Any]], List[str]]:
    projects_field = settings.CODEBASE_MONGO_PROJECTS_FIELD
    codebase_field = settings.CODEBASE_MONGO_CODEBASE_ARRAY_FIELD

    pipeline: List[Dict[str, Any]] = [
        {"$match": {uid_field: user_id}},
        {"$limit": 1},
        {
            "$set": {
                "_projObj": {
                    "$getField": {
                        "field": project_id,
                        "input": f"${projects_field}",
                    }
                },
            }
        },
        {
            "$unwind": {
                "path": f"$_projObj.{codebase_field}",
                "includeArrayIndex": "_codebase_ix",
            }
        },
        {
            "$set": {
                "_path": f"$_projObj.{codebase_field}.{path_field}",
                "_raw": f"$_projObj.{codebase_field}.{content_field}",
            }
        },
        {"$match": {"_raw": {"$regex": escaped, "$options": "i"}}},
        {"$limit": fetch_limit},
        {
            "$project": {
                "_path": 1,
                "_raw": 1,
                "_parent_id": "$_id",
                "_codebase_ix": 1,
            }
        },
    ]

    rows: List[Dict[str, Any]] = []
    contents: List[str] = []
    cursor = collection.aggregate(pipeline)
    async for doc in cursor:
        raw_content = doc.get("_raw") or ""
        text = raw_content if isinstance(raw_content, str) else str(raw_content)
        path_val = doc.get("_path", "")
        parent_id = doc.get("_parent_id")
        ix = doc.get("_codebase_ix")
        sid = f"{parent_id}_{ix}" if parent_id is not None and ix is not None else ""
        rows.append(
            {
                "_path": str(path_val) if path_val is not None else "",
                "_raw": text,
                "_id": sid,
            }
        )
        contents.append(text)
    return rows, contents


async def search_chunks(
    user_id: int,
    query: str,
    top_k: int,
    project_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Find codebase chunks for user_id; flat collection or nested user document + BM25 rank.

    ``nested_user_doc`` expects one document per ``user_id`` with ``projects.<project_id>.codebase``
    as an array of ``{path, content}``. Pass ``project_id`` (validated: letters, digits, ``_``, ``-``).

    Raises:
        RuntimeError: Mongo URI missing or motor not installed.
        ValueError: nested layout without valid ``project_id``.
    """
    if not query or not query.strip():
        return []

    stripped = query.strip()
    query_tokens = tokenize(stripped)

    layout = settings.CODEBASE_MONGO_LAYOUT
    if layout == "nested_user_doc":
        pid = validate_project_id(project_id)
    else:
        pid = None  # flat ignores project_id

    client = _get_client()
    uid_field = settings.CODEBASE_MONGO_USER_ID_FIELD
    path_field = settings.CODEBASE_MONGO_PATH_FIELD
    content_field = settings.CODEBASE_MONGO_CONTENT_FIELD
    db_name = settings.CODEBASE_MONGO_DB
    coll_name = settings.CODEBASE_MONGO_COLLECTION
    preview_max = max(1, settings.CODEBASE_MONGO_PREVIEW_MAX_CHARS)

    escaped = re.escape(stripped)
    top_k_clamped = max(1, min(int(top_k), 100))
    fetch_limit = _bm25_max_candidates_clamped()

    collection = client[db_name][coll_name]

    if layout == "flat":
        rows, contents = await _fetch_rows_flat(
            collection, uid_field, path_field, content_field, user_id, escaped, fetch_limit
        )
    elif layout == "nested_user_doc":
        rows, contents = await _fetch_rows_nested(
            collection,
            uid_field,
            path_field,
            content_field,
            user_id,
            pid,
            escaped,
            fetch_limit,
        )
    else:
        raise RuntimeError(f"Unknown CODEBASE_MONGO_LAYOUT: {layout}")

    if not rows:
        logger.info("codebase_mongo: user_id=%s query=%r hits=0 layout=%s", user_id, query[:80], layout)
        return []

    out = _bm25_rank_slice(rows, contents, query_tokens, stripped, top_k_clamped, preview_max)

    logger.info(
        "codebase_mongo: user_id=%s query=%r layout=%s candidates=%s returned=%s",
        user_id,
        query[:80],
        layout,
        len(rows),
        len(out),
    )
    return out
