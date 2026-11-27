"""RAG 业务服务层：对接上传链路，上传时直接摄入并备份原文到 MySQL。"""

import tempfile  # 创建临时文件
from pathlib import Path

from sqlalchemy.orm import Session

from app.rag import IngestResult, ingest_file, save_chunks


class RagService:
    """RAG 知识库摄入服务。"""

    @staticmethod
    def ingest_from_bytes(
        db: Session,
        file_bytes: bytes,
        file_name: str,
        user_id: int,
        resource_id: int,
        doc_category: str | None = None,
    ) -> IngestResult:
        """上传时直接复用内存中的文件字节，零额外网络 I/O。

        流程：写临时文件 → ingest_file（写 Qdrant） → save_chunks（备份 MySQL） → commit。
        Qdrant 写成功但 MySQL 写失败时事务回滚；。
        #todo:状态机+先库后向量写+失败时按 id/过滤条件删向量+定时任务对账
        """
        suffix = Path(file_name).suffix.lower()

        # 把内存中的字节数据临时写到磁盘 ，让解析库能读取。
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)

        try:
            result = ingest_file(
                file_path=tmp_path,
                user_id=user_id,
                doc_category=doc_category,
                original_file_name=file_name,
            )
            try:
                save_chunks(
                    db=db,
                    resource_id=resource_id,
                    chunks=result.chunks,
                    vector_ids=result.vector_ids,
                )
                db.commit()
            except Exception:
                db.rollback()
                raise
            return result
        finally:
            tmp_path.unlink(missing_ok=True)
