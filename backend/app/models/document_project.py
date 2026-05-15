"""
文档项目数据模型（使用 JSON 文件存储）
"""
import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid


class DocumentProjectStorage:
    """文档项目存储类（基于 JSON 文件）"""

    def __init__(self, storage_dir: str = "./data"):
        self.storage_dir = storage_dir
        self.projects_file = os.path.join(storage_dir, "document_projects.json")
        self._ensure_storage_dir()

    def _ensure_storage_dir(self):
        """确保存储目录存在"""
        os.makedirs(self.storage_dir, exist_ok=True)
        if not os.path.exists(self.projects_file):
            with open(self.projects_file, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().isoformat()

    @staticmethod
    def _default_memory_status() -> Dict[str, Any]:
        return {
            "enabled": True,
            "lastIndexedAt": None,
            "lastRetrievedAt": None,
            "lastRetrievedCount": 0,
            "lastSummaryIndexedAt": None,
        }

    @staticmethod
    def _default_context_config() -> Dict[str, Any]:
        return {
            "summaryTriggerRatio": 0.8,
            "recentTurns": 3,
            "retrievedMemories": 3,
            "maxSourceChunks": 3,
        }

    def _normalize_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        timestamp = message.get("timestamp") or self._now_iso()
        content = message.get("content", "")
        token_estimate = message.get("tokenEstimate")
        if token_estimate is None:
            token_estimate = max(1, len(content.strip()) // 4) if content else 0

        normalized = dict(message)
        normalized.setdefault("id", str(uuid.uuid4()))
        normalized.setdefault("role", "assistant")
        normalized.setdefault("content", content)
        normalized.setdefault("intentType", "general")
        normalized.setdefault("appliedOperation", "none")
        normalized.setdefault("tokenEstimate", token_estimate)
        normalized.setdefault("sourceRefs", [])
        normalized.setdefault("costTrace", {})
        normalized.setdefault("summaryEligible", True)
        normalized.setdefault("contextMeta", {})
        normalized["timestamp"] = timestamp
        return normalized

    def _normalize_conversation(
        self,
        conversation: Dict[str, Any],
        project_id: str,
    ) -> Dict[str, Any]:
        created_at = conversation.get("createdAt") or self._now_iso()
        updated_at = conversation.get("updatedAt") or created_at
        messages = [
            self._normalize_message(message)
            for message in conversation.get("messages", [])
            if isinstance(message, dict)
        ]
        context_config = self._default_context_config()
        context_config.update(conversation.get("contextConfig") or {})
        memory_status = self._default_memory_status()
        memory_status.update(conversation.get("memoryStatus") or {})

        normalized = dict(conversation)
        normalized.setdefault("id", str(uuid.uuid4()))
        normalized.setdefault("scopeType", "project")
        normalized.setdefault("scopeId", project_id)
        normalized.setdefault("title", "新对话")
        normalized.setdefault("rollingSummary", "")
        normalized.setdefault("summaryVersion", 0)
        normalized.setdefault("compactedMessageCount", 0)
        normalized.setdefault("recentWindow", context_config.get("recentTurns", 3))
        normalized.setdefault("tokenBudget", 6000)
        normalized.setdefault("lastCompactedAt", None)
        normalized.setdefault("messages", messages)
        normalized.setdefault("memoryStatus", memory_status)
        normalized.setdefault("contextConfig", context_config)
        normalized["createdAt"] = created_at
        normalized["updatedAt"] = updated_at
        normalized["messages"] = messages
        normalized["memoryStatus"] = memory_status
        normalized["contextConfig"] = context_config
        return normalized

    def _normalize_project(self, project: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(project)
        normalized.setdefault("folderIds", [])
        normalized.setdefault("outline", [])
        normalized.setdefault("outlineLocked", False)
        normalized.setdefault("sections", {})
        normalized.setdefault("conversations", [])
        normalized.setdefault("createdAt", self._now_iso())
        normalized.setdefault("updatedAt", normalized["createdAt"])

        conversations = [
            self._normalize_conversation(conversation, normalized.get("id", ""))
            for conversation in normalized.get("conversations", [])
            if isinstance(conversation, dict)
        ]
        normalized["conversations"] = conversations
        return normalized

    def _load_projects(self) -> List[Dict]:
        """加载项目数据"""
        with open(self.projects_file, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return [
            self._normalize_project(project)
            for project in payload
            if isinstance(project, dict)
        ]

    def _save_projects(self, projects: List[Dict]):
        """保存项目数据"""
        with open(self.projects_file, "w", encoding="utf-8") as f:
            json.dump(projects, f, ensure_ascii=False, indent=2)

    def create_project(
        self,
        title: str,
        folder_ids: List[str],
        outline: Optional[List[Dict]] = None,
        content: Optional[List[Dict]] = None,
        user_id: Optional[int] = None,
    ) -> Dict:
        """创建项目"""
        projects = self._load_projects()

        # 初始化 sections
        sections = {}

        # 如果传入了 content，填充到 sections
        if content:
            for section_data in content:
                section_id = section_data.get("sectionId")
                if section_id:
                    sections[section_id] = section_data

        project = {
            "id": str(uuid.uuid4()),
            "title": title,
            "folderIds": folder_ids,
            "outline": outline,  # 大纲（树形结构）
            "outlineLocked": False,  # 大纲是否已锁定
            "sections": sections,  # 章节 ID -> 章节内容（包含段落和版本）
            "conversations": [],
            "userId": user_id,
            "createdAt": self._now_iso(),
            "updatedAt": self._now_iso(),
        }

        projects.append(project)
        self._save_projects(projects)
        return self._normalize_project(project)

    def get_project(self, project_id: str, user_id: Optional[int] = None) -> Optional[Dict]:
        """获取单个项目"""
        projects = self._load_projects()
        for project in projects:
            if project["id"] == project_id:
                if user_id is not None and project.get("userId") != user_id:
                    continue
                return project
        return None

    def list_projects(
        self,
        skip: int = 0,
        limit: int = 100,
        user_id: Optional[int] = None,
    ) -> tuple[List[Dict], int]:
        """列出项目"""
        projects = self._load_projects()
        if user_id is not None:
            projects = [project for project in projects if project.get("userId") == user_id]

        # 按更新时间倒序排序
        projects.sort(key=lambda x: x.get("updatedAt", ""), reverse=True)

        total = len(projects)

        # 分页
        projects = projects[skip : skip + limit]

        return projects, total

    def update_project(
        self,
        project_id: str,
        user_id: Optional[int] = None,
        **update_data
    ) -> Optional[Dict]:
        """更新项目"""
        projects = self._load_projects()

        for i, project in enumerate(projects):
            if project["id"] == project_id:
                if user_id is not None and project.get("userId") != user_id:
                    continue
                project = self._normalize_project(project)

                # 更新字段
                for key, value in update_data.items():
                    if key == "sections":
                        # 合并 sections
                        project["sections"].update(value)
                    elif key == "conversations":
                        project["conversations"] = [
                            self._normalize_conversation(conversation, project_id)
                            for conversation in value
                            if isinstance(conversation, dict)
                        ]
                    else:
                        project[key] = value

                project["updatedAt"] = self._now_iso()
                projects[i] = project
                self._save_projects(projects)
                return project

        return None

    def update_full_html(
        self,
        project_id: str,
        full_html: str,
        user_id: Optional[int] = None,
    ) -> Optional[Dict]:
        """更新完整的富文本内容"""
        project = self.get_project(project_id, user_id=user_id)
        if not project:
            return None

        projects = self._load_projects()
        for i, p in enumerate(projects):
            if p["id"] == project_id:
                if user_id is not None and p.get("userId") != user_id:
                    continue
                p["full_html"] = full_html
                p["updatedAt"] = self._now_iso()
                projects[i] = p
                self._save_projects(projects)
                return p

        return None

    def update_outline(
        self,
        project_id: str,
        outline: List[Dict],
        locked: bool = False,
        user_id: Optional[int] = None,
    ) -> Optional[Dict]:
        """更新大纲"""
        return self.update_project(project_id, user_id=user_id, outline=outline, outlineLocked=locked)

    def add_section_content(
        self,
        project_id: str,
        section_id: str,
        content: Dict,
        user_id: Optional[int] = None,
    ) -> Optional[Dict]:
        """添加章节内容"""
        project = self.get_project(project_id, user_id=user_id)
        if not project:
            return None

        sections = project.get("sections", {})
        sections[section_id] = content
        return self.update_project(project_id, user_id=user_id, sections=sections)

    def update_paragraph(
        self,
        project_id: str,
        section_id: str,
        paragraph_id: str,
        content: str,
        save_version: bool = True,
        user_id: Optional[int] = None,
    ) -> Optional[Dict]:
        """更新段落内容（支持版本管理）"""
        project = self.get_project(project_id, user_id=user_id)
        if not project:
            return None

        sections = project.get("sections", {})
        section = sections.get(section_id, {})
        paragraphs = section.get("paragraphs", [])

        # 找到段落（使用 paragraph_id 字段）
        for para in paragraphs:
            if para.get("paragraph_id") == paragraph_id:
                # 保存旧版本
                if save_version:
                    versions = para.get("versions", [])
                    versions.append({
                        "content": para.get("content", ""),
                        "timestamp": para.get("timestamp", self._now_iso()),
                    })
                    para["versions"] = versions

                # 更新内容
                para["content"] = content
                para["timestamp"] = self._now_iso()

                section["paragraphs"] = paragraphs
                sections[section_id] = section
                return self.update_project(project_id, user_id=user_id, sections=sections)

        return None

    def restore_paragraph_version(
        self,
        project_id: str,
        section_id: str,
        paragraph_id: str,
        version_index: int,
        user_id: Optional[int] = None,
    ) -> Optional[Dict]:
        """恢复段落到指定版本"""
        project = self.get_project(project_id, user_id=user_id)
        if not project:
            return None

        sections = project.get("sections", {})
        section = sections.get(section_id, {})
        paragraphs = section.get("paragraphs", [])

        # 找到段落（使用 paragraph_id 字段）
        for para in paragraphs:
            if para.get("paragraph_id") == paragraph_id:
                versions = para.get("versions", [])
                if 0 <= version_index < len(versions):
                    # 保存当前版本
                    current_version = {
                        "content": para.get("content", ""),
                        "timestamp": para.get("timestamp", self._now_iso()),
                        "sources": para.get("sources", [])
                    }
                    versions.append(current_version)

                    # 恢复到指定版本
                    target_version = versions[version_index]
                    para["content"] = target_version.get("content", "")
                    para["timestamp"] = self._now_iso()

                    # 更新版本列表（移除被恢复的版本，因为它已成为当前版本）
                    para["versions"] = versions[:version_index] + versions[version_index + 1:]

                    section["paragraphs"] = paragraphs
                    sections[section_id] = section
                    return self.update_project(project_id, user_id=user_id, sections=sections)

        return None

    def update_project_content(
        self,
        project_id: str,
        sections: List[Dict],
        user_id: Optional[int] = None,
    ) -> Optional[Dict]:
        """更新项目内容（富文本编辑器保存）"""
        project = self.get_project(project_id, user_id=user_id)
        if not project:
            return None

        # 构建新的 sections 字典
        new_sections = {}

        for section_data in sections:
            section_id = section_data.get("sectionId")
            if not section_id:
                continue

            # 转换为后端存储格式
            paragraphs = []
            for para_data in section_data.get("paragraphs", []):
                paragraph = {
                    "paragraph_id": str(uuid.uuid4()),
                    "section_id": section_id,
                    "content": para_data.get("content", ""),
                    "html_content": para_data.get("html_content", ""),  # 新增：保存富文本格式
                    "sources": para_data.get("sources", []),
                    "timestamp": self._now_iso(),
                    "versions": []
                }
                paragraphs.append(paragraph)

            new_sections[section_id] = {
                "sectionId": section_id,
                "paragraphs": paragraphs,
                "sources": []
            }

        # 更新项目
        project["sections"] = new_sections
        project["updatedAt"] = self._now_iso()

        # 保存到文件
        projects = self._load_projects()
        for i, p in enumerate(projects):
            if p["id"] == project_id:
                projects[i] = project
                break

        self._save_projects(projects)
        return project

    def create_conversation(
        self,
        project_id: str,
        scope_type: str,
        scope_id: str,
        title: str,
        initial_message: Optional[Dict[str, Any]] = None,
        recent_window: int = 6,
        token_budget: int = 6000,
        user_id: Optional[int] = None,
    ) -> Optional[Dict]:
        """为项目创建写作会话"""
        project = self.get_project(project_id, user_id=user_id)
        if not project:
            return None

        conversation = self._normalize_conversation(
            {
                "id": str(uuid.uuid4()),
                "scopeType": scope_type,
                "scopeId": scope_id,
                "title": title,
                "messages": [initial_message] if initial_message else [],
                "rollingSummary": "",
                "summaryVersion": 0,
                "compactedMessageCount": 0,
                "recentWindow": recent_window,
                "tokenBudget": token_budget,
                "lastCompactedAt": None,
                "memoryStatus": self._default_memory_status(),
                "contextConfig": {
                    **self._default_context_config(),
                    "recentTurns": recent_window,
                },
                "createdAt": self._now_iso(),
                "updatedAt": self._now_iso(),
            },
            project_id,
        )

        conversations = project.get("conversations", [])
        conversations.insert(0, conversation)
        self.update_project(project_id, user_id=user_id, conversations=conversations)
        return conversation

    def list_conversations(
        self,
        project_id: str,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> List[Dict]:
        """列出项目下的会话"""
        project = self.get_project(project_id, user_id=user_id)
        if not project:
            return []

        conversations = project.get("conversations", [])
        if scope_type:
            conversations = [item for item in conversations if item.get("scopeType") == scope_type]
        if scope_id:
            conversations = [item for item in conversations if item.get("scopeId") == scope_id]
        conversations.sort(key=lambda item: item.get("updatedAt", ""), reverse=True)
        return conversations

    def get_conversation(self, project_id: str, conversation_id: str, user_id: Optional[int] = None) -> Optional[Dict]:
        """获取项目下的单个会话"""
        conversations = self.list_conversations(project_id, user_id=user_id)
        for conversation in conversations:
            if conversation.get("id") == conversation_id:
                return conversation
        return None

    def update_conversation(
        self,
        project_id: str,
        conversation_id: str,
        user_id: Optional[int] = None,
        **update_data: Any,
    ) -> Optional[Dict]:
        """更新会话元数据或消息列表"""
        projects = self._load_projects()

        for project_index, project in enumerate(projects):
            if project.get("id") != project_id:
                continue
            if user_id is not None and project.get("userId") != user_id:
                continue

            conversations = project.get("conversations", [])
            for conversation_index, conversation in enumerate(conversations):
                if conversation.get("id") != conversation_id:
                    continue

                updated_conversation = dict(conversation)
                for key, value in update_data.items():
                    updated_conversation[key] = value

                updated_conversation["updatedAt"] = self._now_iso()
                conversations[conversation_index] = self._normalize_conversation(
                    updated_conversation,
                    project_id,
                )
                project["conversations"] = conversations
                project["updatedAt"] = self._now_iso()
                projects[project_index] = project
                self._save_projects(projects)
                return conversations[conversation_index]

        return None

    def add_conversation_message(
        self,
        project_id: str,
        conversation_id: str,
        message: Dict[str, Any],
        user_id: Optional[int] = None,
    ) -> Optional[Dict]:
        """向会话追加消息"""
        conversation = self.get_conversation(project_id, conversation_id, user_id=user_id)
        if not conversation:
            return None

        messages = conversation.get("messages", [])
        messages.append(self._normalize_message(message))
        return self.update_conversation(project_id, conversation_id, user_id=user_id, messages=messages)

    def replace_section_paragraph(
        self,
        project_id: str,
        section_id: str,
        content: str,
        sources: Optional[List[Dict[str, Any]]] = None,
        user_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """使用新内容替换章节当前段落，并保留旧版本"""
        project = self.get_project(project_id, user_id=user_id)
        if not project:
            return None

        sections = project.get("sections", {})
        section = sections.get(section_id, {"sectionId": section_id, "paragraphs": [], "sources": []})
        paragraphs = section.get("paragraphs", [])
        versions = []

        if paragraphs:
            current_paragraph = paragraphs[-1]
            versions = list(current_paragraph.get("versions", []))
            versions.append(
                {
                    "content": current_paragraph.get("content", ""),
                    "timestamp": current_paragraph.get("timestamp", self._now_iso()),
                    "sources": current_paragraph.get("sources", []),
                }
            )

        updated_paragraph = {
            "paragraph_id": str(uuid.uuid4()),
            "section_id": section_id,
            "content": content,
            "sources": sources or [],
            "timestamp": self._now_iso(),
            "versions": versions,
        }

        section["paragraphs"] = [updated_paragraph]
        section["sources"] = sources or []
        sections[section_id] = section
        self.update_project(project_id, user_id=user_id, sections=sections)
        return updated_paragraph

    def delete_project(self, project_id: str, user_id: Optional[int] = None) -> bool:
        """删除项目"""
        projects = self._load_projects()

        for i, project in enumerate(projects):
            if project["id"] == project_id:
                if user_id is not None and project.get("userId") != user_id:
                    continue
                projects.pop(i)
                self._save_projects(projects)
                return True

        return False


# 全局存储实例
document_project_storage = DocumentProjectStorage()
