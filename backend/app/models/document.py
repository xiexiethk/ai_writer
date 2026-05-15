"""
文档数据模型（使用 JSON 文件存储）
"""
import json
import os
from datetime import datetime
from typing import List, Optional, Dict
import uuid
from app.schemas.document import DocumentCreate, DocumentUpdate, ParseStatus, FileType


class DocumentStorage:
    """文档存储类（基于 JSON 文件）"""

    def __init__(self, storage_dir: str = "./data"):
        self.storage_dir = storage_dir
        self.documents_file = os.path.join(storage_dir, "documents.json")
        self.folders_file = os.path.join(storage_dir, "folders.json")
        self._ensure_storage_dir()
        self.folders = self._load_folders()

    def _ensure_storage_dir(self):
        """确保存储目录存在"""
        os.makedirs(self.storage_dir, exist_ok=True)
        if not os.path.exists(self.documents_file):
            with open(self.documents_file, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
        if not os.path.exists(self.folders_file):
            # 初始化默认文件夹
            default_folders = [
                {
                    "id": "root",
                    "name": "根目录",
                    "parentId": None,
                    "createdAt": datetime.now().isoformat(),
                }
            ]
            with open(self.folders_file, "w", encoding="utf-8") as f:
                json.dump(default_folders, f, ensure_ascii=False, indent=2)

    def _load_documents(self) -> List[Dict]:
        """加载文档数据"""
        with open(self.documents_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_folders(self) -> List[Dict]:
        """加载文件夹数据"""
        with open(self.folders_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_documents(self, documents: List[Dict]):
        """保存文档数据"""
        with open(self.documents_file, "w", encoding="utf-8") as f:
            json.dump(documents, f, ensure_ascii=False, indent=2)

    def create_document(self, data: DocumentCreate, file_path: str, pdf_path: Optional[str] = None) -> Dict:
        """创建文档"""
        documents = self._load_documents()

        doc = {
            "id": str(uuid.uuid4()),
            "title": data.title,
            "fileName": data.fileName,
            "fileType": data.fileType.value,
            "fileSize": data.fileSize,
            "uploadTime": datetime.now().isoformat(),
            "parsed": False,
            "parseStatus": ParseStatus.PENDING.value,
            "chunked": False,  # 初始分块状态为未分块
            "vectorizeStatus": "pending",  # 向量化状态
            "tags": data.tags,
            "folderId": data.folderId,
            "filePath": file_path,
            "pdfPath": pdf_path,  # 转换后的 PDF 路径（如果原始文件不是 PDF）
        }

        documents.append(doc)
        self._save_documents(documents)
        return doc

    def create_document_with_markdown(
        self,
        data: DocumentCreate,
        file_path: str,
        pdf_path: Optional[str] = None,
        markdown_content: Optional[str] = None
    ) -> Dict:
        """创建文档（带 Markdown 内容）"""
        documents = self._load_documents()

        doc = {
            "id": str(uuid.uuid4()),
            "title": data.title,
            "fileName": data.fileName,
            "fileType": data.fileType.value,
            "fileSize": data.fileSize,
            "uploadTime": datetime.now().isoformat(),
            "parsed": True,  # 已经有 Markdown，标记为已解析
            "parseStatus": ParseStatus.SUCCESS.value,
            "markdownContent": markdown_content,
            "chunked": False,
            "vectorizeStatus": "pending",
            "tags": data.tags,
            "folderId": data.folderId,
            "filePath": file_path,
            "pdfPath": pdf_path,
        }

        documents.append(doc)
        self._save_documents(documents)
        return doc

    def get_document(self, document_id: str) -> Optional[Dict]:
        """获取单个文档"""
        documents = self._load_documents()
        for doc in documents:
            if doc["id"] == document_id:
                return doc
        return None

    def list_documents(
        self,
        folder: Optional[str] = None,
        tag: Optional[str] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[List[Dict], int]:
        """列出文档"""
        documents = self._load_documents()

        # 筛选
        if folder:
            documents = [doc for doc in documents if doc["folderId"] == folder]
        if tag:
            documents = [doc for doc in documents if tag in doc.get("tags", [])]
        if search:
            search_lower = search.lower()
            documents = [
                doc
                for doc in documents
                if search_lower in doc["title"].lower()
                or search_lower in doc["fileName"].lower()
            ]

        total = len(documents)

        # 分页
        documents = documents[skip : skip + limit]

        return documents, total

    def update_document(self, document_id: str, data: DocumentUpdate) -> Optional[Dict]:
        """更新文档"""
        documents = self._load_documents()

        for i, doc in enumerate(documents):
            if doc["id"] == document_id:
                update_data = data.model_dump(exclude_unset=True)

                # 处理特殊字段
                if "markdownContent" in update_data:
                    doc["markdownContent"] = update_data["markdownContent"]

                if "tags" in update_data:
                    doc["tags"] = update_data["tags"]

                if "title" in update_data:
                    doc["title"] = update_data["title"]

                if "folderId" in update_data:
                    doc["folderId"] = update_data["folderId"]

                documents[i] = doc
                self._save_documents(documents)
                return doc

        return None

    def delete_document(self, document_id: str) -> bool:
        """删除文档"""
        documents = self._load_documents()

        for i, doc in enumerate(documents):
            if doc["id"] == document_id:
                # 删除文件
                file_path = doc.get("filePath")
                if file_path and os.path.exists(file_path):
                    os.remove(file_path)

                documents.pop(i)
                self._save_documents(documents)
                return True

        return False

    def update_parse_status(
        self,
        document_id: str,
        status: ParseStatus,
        markdown_content: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Optional[Dict]:
        """更新解析状态"""
        documents = self._load_documents()

        for i, doc in enumerate(documents):
            if doc["id"] == document_id:
                doc["parseStatus"] = status.value
                doc["parsed"] = status == ParseStatus.SUCCESS

                if markdown_content is not None:
                    doc["markdownContent"] = markdown_content

                if error_message is not None:
                    doc["errorMessage"] = error_message

                documents[i] = doc
                self._save_documents(documents)
                return doc

        return None

    def update_chunked_status(self, document_id: str, chunked: bool = True) -> Optional[Dict]:
        """更新分块状态"""
        documents = self._load_documents()

        for i, doc in enumerate(documents):
            if doc["id"] == document_id:
                doc["chunked"] = chunked
                documents[i] = doc
                self._save_documents(documents)
                return doc

        return None

    def update_vectorize_status(
        self, document_id: str, status: str, chunk_count: int = None
    ) -> Optional[Dict]:
        """更新向量化状态"""
        documents = self._load_documents()

        for i, doc in enumerate(documents):
            if doc["id"] == document_id:
                doc["vectorizeStatus"] = status
                if status == "success":
                    doc["chunked"] = True
                if chunk_count is not None:
                    doc["chunkCount"] = chunk_count
                documents[i] = doc
                self._save_documents(documents)
                return doc

        return None

    def save_parse_result(
        self, document_id: str, markdown_content: str, images: Optional[List[str]] = None
    ) -> Optional[Dict]:
        """保存解析结果"""
        documents = self._load_documents()

        for i, doc in enumerate(documents):
            if doc["id"] == document_id:
                doc["parsed"] = True
                doc["parseStatus"] = ParseStatus.SUCCESS.value
                doc["markdownContent"] = markdown_content

                # 如果之前有错误信息，清除它
                if "errorMessage" in doc:
                    del doc["errorMessage"]

                documents[i] = doc
                self._save_documents(documents)
                return doc

        return None

    def update_document_metadata(self, document_id: str, metadata: Dict) -> Optional[Dict]:
        """更新文档元数据"""
        documents = self._load_documents()

        for i, doc in enumerate(documents):
            if doc["id"] == document_id:
                if "metadata" not in doc:
                    doc["metadata"] = {}
                doc["metadata"].update(metadata)

                documents[i] = doc
                self._save_documents(documents)
                return doc

        return None


# 全局存储实例
storage = DocumentStorage()
