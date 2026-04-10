from __future__ import annotations

from pathlib import Path

from app.core.settings import settings


BACKEND_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_AI_LAB_ROOT = BACKEND_ROOT.parents[2]
JVT_TECHNOLOGIES_ROOT = PRIVATE_AI_LAB_ROOT / "JVT-Technologies"


def _resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return BACKEND_ROOT / path


def resolve_storage_root() -> Path:
    return _resolve_path(settings.storage_root)


def resolve_vector_data_root() -> Path:
    configured_root = settings.vector_data_root.strip()
    if configured_root:
        return _resolve_path(configured_root)
    return resolve_storage_root()


def resolve_model_artifact_root() -> Path:
    return _resolve_path(settings.model_artifact_root)


def resolve_embedding_cache_root() -> Path:
    configured_root = settings.embedding_cache_root.strip()
    if configured_root:
        return _resolve_path(configured_root)
    return resolve_model_artifact_root() / "embeddings"


def resolve_answer_model_cache_root() -> Path:
    configured_root = settings.answer_model_cache_root.strip()
    if configured_root:
        return _resolve_path(configured_root)
    return resolve_model_artifact_root() / "answers"


def resolve_demo_static_root() -> Path:
    return BACKEND_ROOT / "app" / "static"


def resolve_jvt_demo_sample_root() -> Path:
    return JVT_TECHNOLOGIES_ROOT / "demo-packaging" / "sample-documents"
