"""knowledge_chunks 表的读写工具。"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.tables import KnowledgeChunk


def save_chunks(
    db: Session,
    resource_id: int,
    chunks: list[str],
    vector_ids: list[str],
) -> int:
    """批量写入切片：先删旧记录再插入，仅 flush 不 commit。"""
    if not chunks or not vector_ids:
        return 0
    if len(chunks) != len(vector_ids):
        raise ValueError("chunks 与 vector_ids 长度不一致")

    db.query(KnowledgeChunk).filter(
        KnowledgeChunk.resource_id == resource_id
        #不自动同步受影响对象，较少性能开销
    ).delete(synchronize_session=False)


    db.add_all([
        KnowledgeChunk(
            resource_id=resource_id,
            chunk_index=index,
            text=text,
            char_count=len(text),
            vector_id=vid,
        )
        for index, (text, vid) in enumerate(zip(chunks, vector_ids))
    ])
    # flush：将文件内容，写入内存缓冲区、同步到磁盘临时缓存，但没点保存
    db.flush()
    print(f"[RAG][MySQL] 写入 {len(chunks)} 条 knowledge_chunks，resource_id={resource_id}")
    return len(chunks)


def delete_chunks_by_resource(db: Session, resource_id: int) -> int:
    """删除指定资源的全部切片记录。"""
    deleted = db.query(KnowledgeChunk).filter(
        KnowledgeChunk.resource_id == resource_id
    ).delete(synchronize_session=False)
    db.flush()
    return deleted


def fetch_chunks_by_vector_ids(
    db: Session,
    vector_ids: list[str],
) -> dict[str, KnowledgeChunk]:
    """根据 vector_id 列表批量回查，返回 {vector_id: KnowledgeChunk}。"""
    if not vector_ids:
        return {}

    rows = db.scalars(
        select(KnowledgeChunk).where(KnowledgeChunk.vector_id.in_(vector_ids))
    ).all()
    return {row.vector_id: row for row in rows}
