"""RAG 知识库构建领域工具：文件解析 → 分块 → 向量化 → Qdrant 写入 + MySQL 备份。"""

from app.rag.chunk_store import (
    delete_chunks_by_resource,
    fetch_chunks_by_vector_ids,
    save_chunks,
)
from app.rag.core import (
    CATEGORY_GENERAL,
    CATEGORY_RESUME,
    CATEGORY_STUDY,
    SUPPORTED_CATEGORIES,
    IngestResult,
    infer_doc_category,
    ingest_file,
)
from app.rag.retriever import (
    search_similar_chunks,
    should_retrieve,
)

__all__ = [
    "CATEGORY_GENERAL",
    "CATEGORY_RESUME",
    "CATEGORY_STUDY",
    "SUPPORTED_CATEGORIES",
    "IngestResult",
    "infer_doc_category",
    "ingest_file",
    "save_chunks",
    "delete_chunks_by_resource",
    "fetch_chunks_by_vector_ids",
    "search_similar_chunks",
    "should_retrieve",
]
