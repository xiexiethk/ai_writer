"""
文档项目相关 API 路由
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse, HTMLResponse, Response
from pydantic import BaseModel, Field
from typing import List, Optional
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn  # 用于设置字体
from docx.oxml import OxmlElement
import io
import re
from urllib.parse import quote
import markdown
from bs4 import BeautifulSoup
import logging
from sqlalchemy import select

from app.api.auth import get_current_user, get_user_by_token
from app.core.database import AsyncSessionLocal
from app.models.document_db import Document as DocumentDB
from app.models.document_project import document_project_storage
from app.models.user import User
from app.services.document_generator import document_generator_service
from app.services.report_conversation_service import report_conversation_service

logger = logging.getLogger(__name__)


async def get_project_document_ids(project: dict, user_id: int) -> List[str]:
    """获取当前用户在项目所选知识库下的已解析文档ID。"""
    folder_ids = project.get("folderIds", []) or []
    if not folder_ids:
        return []

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(DocumentDB.id).where(
                DocumentDB.user_id == user_id,
                DocumentDB.parsed == True,
                DocumentDB.folder_id.in_(folder_ids),
            )
        )
        return [row[0] for row in result.all()]


def get_owned_project_or_404(project_id: str, user_id: int) -> dict:
    """获取当前用户拥有的项目，不存在或无权访问时抛 404。"""
    project = document_project_storage.get_project(project_id, user_id=user_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def convert_quotes_to_chinese(text):
    """
    将英文引号转换为中文引号
    如果引号内的文本包含中文字符，使用中文引号
    """
    def replace_double_quotes(match):
        content = match.group(1)
        # 如果内容包含中文字符，使用中文引号
        if any('\u4e00' <= char <= '\u9fff' for char in content):
            return '\u201c' + content + '\u201d'  # 中文引号 U+201C U+201D
        else:
            return match.group(0)  # 保持原样（英文引号）

    def replace_single_quotes(match):
        content = match.group(1)
        # 如果内容包含中文字符，使用中文引号
        if any('\u4e00' <= char <= '\u9fff' for char in content):
            return '\u2018' + content + '\u2019'  # 中文引号 U+2018 U+2019
        else:
            return match.group(0)  # 保持原样（英文引号）

    # 处理双引号 "..."
    text = re.sub(r'"([^"]+)"', replace_double_quotes, text)
    # 处理单引号 '...'
    text = re.sub(r"'([^']+)'", replace_single_quotes, text)

    return text


def add_markdown_to_paragraph(paragraph, md_text):
    """
    将 Markdown 文本添加到段落，保留格式（粗体、斜体、代码、行内公式等）
    块级公式不在此函数中处理
    中文引号使用宋体，英文内容使用Times New Roman
    """
    # 先将英文引号转换为中文引号
    md_text = convert_quotes_to_chinese(md_text)

    # 使用占位符保存格式化文本
    placeholders = {}
    placeholder_count = [0]

    def get_placeholder():
        placeholder_count[0] += 1
        return f"__PLACEHOLDER_{placeholder_count[0]}__"

    # 第零步：处理行内公式 $...$
    def replace_math_inline(text):
        # 行内公式 $...$
        lines = text.split('\n')
        result_lines = []
        for line in lines:
            # 对每一行，替换$...$为占位符
            def replace_inline_in_line(match):
                key = get_placeholder()
                placeholders[key] = (match.group(1), 'math-inline')
                return key
            line = re.sub(r'\$([^$]+?)\$', replace_inline_in_line, line)
            result_lines.append(line)
        return '\n'.join(result_lines)

    # 第一步：处理粗体 **text**
    def replace_bold(text):
        pattern = r'\*\*(.+?)\*\*'
        def replacement(match):
            key = get_placeholder()
            placeholders[key] = (match.group(1), 'bold')
            return key
        return re.sub(pattern, replacement, text)

    # 第二步：处理斜体 *text*（避免匹配 **）
    def replace_italic(text):
        pattern = r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)'
        def replacement(match):
            key = get_placeholder()
            placeholders[key] = (match.group(1), 'italic')
            return key
        return re.sub(pattern, replacement, text)

    # 第三步：处理代码 `text`
    def replace_code(text):
        pattern = r'`(.+?)`'
        def replacement(match):
            key = get_placeholder()
            placeholders[key] = (match.group(1), 'code')
            return key
        return re.sub(pattern, replacement, text)

    # 按顺序替换（行内公式优先）
    result = replace_math_inline(md_text)
    result = replace_bold(result)
    result = replace_italic(result)
    result = replace_code(result)

    # 还原并添加到段落
    parts = re.split(r'(__PLACEHOLDER_\d+__)', result)

    # 中文引号字符列表（使用Unicode编码）
    chinese_quotes = ['\u201c', '\u201d', '\u2018', '\u2019', '\u300c', '\u300d', '\u300e', '\u300f']

    for part in parts:
        if part in placeholders:
            text, fmt_type = placeholders[part]

            # 特殊处理：行内公式
            if fmt_type == 'math-inline':
                try:
                    from latex2word import LatexToWordElement
                    latex_to_word = LatexToWordElement(text)
                    latex_to_word.add_latex_to_paragraph(paragraph)
                    logger.debug(f"行内公式已添加到段落")
                except Exception as e:
                    import traceback
                    logger.error(f"行内公式转换失败: {e}\nLaTeX: {text[:50]}...\nTraceback: {traceback.format_exc()}")
                continue

            # 普通格式化文本
            for char in text:
                run = paragraph.add_run(char)

                # 如果是中文引号，设置为宋体
                if char in chinese_quotes:
                    run.font.name = '宋体'
                    run.font.size = Pt(12)
                    run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
                else:
                    # 普通文本设置格式
                    if fmt_type == 'bold':
                        run.bold = True
                    elif fmt_type == 'italic':
                        run.italic = True
                    elif fmt_type == 'code':
                        run.font.name = 'Courier New'
                        run.font.size = Pt(10)

        else:
            # 普通文本，逐个字符处理
            if part:
                for char in part:
                    run = paragraph.add_run(char)

                    # 如果是中文引号，设置为宋体
                    if char in chinese_quotes:
                        run.font.name = '宋体'
                        run.font.size = Pt(12)
                        run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')




router = APIRouter()


class CreateProjectRequest(BaseModel):
    """创建项目请求"""
    title: str = Field(..., description="项目标题")
    folderIds: List[str] = Field(default=[], description="知识库ID列表")
    outline: Optional[List[dict]] = Field(None, description="大纲树形结构")
    content: Optional[List[dict]] = Field(None, description="章节内容")


class UpdateOutlineRequest(BaseModel):
    """更新大纲请求"""
    outline: List[dict] = Field(..., description="大纲树形结构")
    locked: bool = Field(False, description="是否锁定大纲")


class GenerateOutlineRequest(BaseModel):
    """生成大纲请求"""
    topic: str = Field(..., description="研究主题")


class CreateConversationRequest(BaseModel):
    """创建报告写作会话请求"""
    scopeType: str = Field(..., description="会话范围: project 或 section")
    scopeId: Optional[str] = Field(None, description="范围ID；项目级可为空，章节级传 sectionId")
    title: Optional[str] = Field(None, description="会话标题")


class SendConversationMessageRequest(BaseModel):
    """发送报告写作会话消息请求"""
    message: str = Field(..., description="用户消息")
    applyMode: str = Field("suggest_only", description="suggest_only 或 apply_to_section")
    targetSectionId: Optional[str] = Field(None, description="需要应用内容的章节ID")


@router.post("")
async def create_project(
    request: CreateProjectRequest,
    current_user: User = Depends(get_current_user),
):
    """
    创建文档项目

    创建新的文档生成项目，可以选择多个知识库，也可以直接传入大纲和内容
    """
    try:
        project = document_project_storage.create_project(
            title=request.title,
            folder_ids=request.folderIds,
            outline=request.outline,
            content=request.content,
            user_id=current_user.id,
        )
        return project

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建项目失败: {str(e)}")


@router.get("")
async def list_projects(
    skip: int = Query(0, description="跳过数量"),
    limit: int = Query(20, description="返回数量"),
    current_user: User = Depends(get_current_user),
):
    """
    获取项目列表

    获取所有文档项目
    """
    try:
        projects, total = document_project_storage.list_projects(
            skip=skip,
            limit=limit,
            user_id=current_user.id,
        )

        return {
            "projects": projects,
            "total": total
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取项目列表失败: {str(e)}")


@router.get("/{project_id}")
async def get_project(project_id: str, current_user: User = Depends(get_current_user)):
    """
    获取项目详情

    获取项目的完整信息，包括大纲和内容
    """
    try:
        return get_owned_project_or_404(project_id, current_user.id)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取项目失败: {str(e)}")


@router.get("/{project_id}/conversations")
async def list_conversations(
    project_id: str,
    scopeType: Optional[str] = Query(None, description="project 或 section"),
    scopeId: Optional[str] = Query(None, description="范围ID"),
    current_user: User = Depends(get_current_user),
):
    """列出项目下的写作会话。"""
    try:
        project = get_owned_project_or_404(project_id, current_user.id)

        conversations = report_conversation_service.list_conversations(
            project_id=project_id,
            scope_type=scopeType,
            scope_id=scopeId,
            user_id=current_user.id,
        )
        return {
            "conversations": conversations,
            "total": len(conversations),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取写作会话失败: {str(e)}")


@router.post("/{project_id}/conversations")
async def create_conversation(
    project_id: str,
    request: CreateConversationRequest,
    current_user: User = Depends(get_current_user),
):
    """创建项目级或章节级写作会话。"""
    try:
        project = get_owned_project_or_404(project_id, current_user.id)

        scope_type = request.scopeType.strip().lower()
        if scope_type not in {"project", "section"}:
            raise HTTPException(status_code=400, detail="scopeType 仅支持 project 或 section")

        scope_id = request.scopeId or project_id
        if scope_type == "section" and not request.scopeId:
            raise HTTPException(status_code=400, detail="章节级会话必须提供 scopeId")

        conversation = report_conversation_service.create_conversation(
            project_id=project_id,
            scope_type=scope_type,
            scope_id=scope_id,
            title=request.title,
            user_id=current_user.id,
        )
        if not conversation:
            raise HTTPException(status_code=404, detail="项目不存在")
        return conversation
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建写作会话失败: {str(e)}")


@router.get("/{project_id}/conversations/{conversation_id}")
async def get_conversation(
    project_id: str,
    conversation_id: str,
    current_user: User = Depends(get_current_user),
):
    """获取写作会话详情。"""
    try:
        get_owned_project_or_404(project_id, current_user.id)

        conversation = report_conversation_service.get_conversation(
            project_id=project_id,
            conversation_id=conversation_id,
            user_id=current_user.id,
        )
        if not conversation:
            raise HTTPException(status_code=404, detail="会话不存在")
        return conversation
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取写作会话失败: {str(e)}")


@router.post("/{project_id}/conversations/{conversation_id}/messages")
async def send_conversation_message(
    project_id: str,
    conversation_id: str,
    request: SendConversationMessageRequest,
    current_user: User = Depends(get_current_user),
):
    """发送写作会话消息，并根据需要应用到章节。"""
    try:
        project = get_owned_project_or_404(project_id, current_user.id)

        apply_mode = request.applyMode.strip().lower()
        if apply_mode not in {"suggest_only", "apply_to_section"}:
            raise HTTPException(status_code=400, detail="applyMode 仅支持 suggest_only 或 apply_to_section")

        document_ids = await get_project_document_ids(project, current_user.id)
        result = await report_conversation_service.send_message(
            project_id=project_id,
            conversation_id=conversation_id,
            user_input=request.message,
            apply_mode=apply_mode,
            target_section_id=request.targetSectionId,
            document_ids=document_ids,
            user_id=current_user.id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"发送写作消息失败: {str(e)}")


@router.put("/{project_id}/outline")
async def update_outline(
    project_id: str,
    request: UpdateOutlineRequest,
    current_user: User = Depends(get_current_user),
):
    """
    更新大纲

    更新项目的大纲并设置锁定状态
    """
    try:
        project = get_owned_project_or_404(project_id, current_user.id)

        current_locked = project.get("outlineLocked", False)

        # 只有在当前已锁定且请求保持锁定状态时才拒绝修改
        # 允许解锁操作（locked=False）或首次锁定
        if current_locked and request.locked:
            raise HTTPException(status_code=400, detail="大纲已锁定，无法修改")

        updated_project = document_project_storage.update_outline(
            project_id=project_id,
            outline=request.outline,
            locked=request.locked,
            user_id=current_user.id,
        )

        return updated_project

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新大纲失败: {str(e)}")


@router.post("/{project_id}/generate-outline")
async def generate_outline(
    project_id: str,
    request: GenerateOutlineRequest,
    current_user: User = Depends(get_current_user),
):
    """
    生成大纲

    基于研究主题和知识库内容自动生成文档大纲
    """
    try:
        project = get_owned_project_or_404(project_id, current_user.id)

        # 检查大纲是否已锁定
        if project.get("outlineLocked", False):
            raise HTTPException(status_code=400, detail="大纲已锁定，无法重新生成")

        # 生成大纲
        outline = await document_generator_service.generate_outline(
            topic=request.topic,
            folder_ids=project.get("folderIds", []),
            user_id=current_user.id,
        )

        # 更新项目
        updated_project = document_project_storage.update_outline(
            project_id=project_id,
            outline=outline,
            locked=False,  # 生成后不锁定，需要用户确认
            user_id=current_user.id,
        )

        return updated_project

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成大纲失败: {str(e)}")


@router.delete("/{project_id}")
async def delete_project(project_id: str, current_user: User = Depends(get_current_user)):
    """
    删除项目

    删除文档项目
    """
    try:
        success = document_project_storage.delete_project(project_id, user_id=current_user.id)
        if not success:
            raise HTTPException(status_code=404, detail="项目不存在")

        return {"message": "删除成功"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除项目失败: {str(e)}")


class GenerateContentRequest(BaseModel):
    """生成内容请求"""
    sectionId: str = Field(..., description="章节ID")
    sectionTitle: str = Field(..., description="章节标题")
    contextSections: List[str] = Field(default=[], description="上下文章节路径")
    customPrompt: str = Field(default="", description="自定义生成需求")


class RegenerateParagraphRequest(BaseModel):
    """重新生成段落请求"""
    sectionId: str = Field(..., description="章节ID")
    sectionTitle: str = Field(..., description="章节标题")
    contextSections: List[str] = Field(default=[], description="上下文章节路径")
    customPrompt: str = Field(default="", description="自定义生成需求")


class UpdateParagraphRequest(BaseModel):
    """更新段落请求"""
    sectionId: str = Field(..., description="章节ID")
    paragraphId: str = Field(..., description="段落ID")
    content: str = Field(..., description="段落内容")


@router.post("/{project_id}/generate-content")
async def generate_section_content(
    project_id: str,
    request: GenerateContentRequest,
    current_user: User = Depends(get_current_user),
):
    """
    生成章节内容

    为指定章节生成内容，基于RAG检索的相关内容
    """
    try:
        project = get_owned_project_or_404(project_id, current_user.id)

        # 获取所有文档ID
        document_ids = await get_project_document_ids(project, current_user.id)

        # 获取完整大纲（用于上下文）
        outline = project.get("outline", [])

        # 生成内容
        result = await document_generator_service.generate_section_content(
            section_title=request.sectionTitle,
            section_id=request.sectionId,
            document_ids=document_ids,
            context_sections=request.contextSections if request.contextSections else None,
            custom_prompt=request.customPrompt if request.customPrompt else None,
            full_outline=outline,  # 传递完整大纲
            user_id=current_user.id,
        )

        # 保存到项目
        document_project_storage.add_section_content(
            project_id=project_id,
            section_id=request.sectionId,
            content={
                "sectionId": request.sectionId,
                "paragraphs": [result],
                "sources": result.get("sources", [])
            },
            user_id=current_user.id,
        )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成内容失败: {str(e)}")


@router.post("/{project_id}/regenerate-paragraph")
async def regenerate_paragraph(
    project_id: str,
    request: RegenerateParagraphRequest,
    current_user: User = Depends(get_current_user),
):
    """
    重新生成段落

    重新生成指定章节的段落内容，保存旧版本到versions中
    """
    try:
        project = get_owned_project_or_404(project_id, current_user.id)

        # 获取所有文档ID
        document_ids = await get_project_document_ids(project, current_user.id)

        # 获取当前段落（用于保存版本）
        sections = project.get("sections", {})
        section = sections.get(request.sectionId, {})
        paragraphs = section.get("paragraphs", [])

        # 准备当前段落信息和版本历史
        current_paragraph = None
        existing_versions = []

        if paragraphs:
            # 获取最新的段落
            current_paragraph = paragraphs[-1]
            # 获取已有的历史版本
            existing_versions = current_paragraph.get("versions", [])

        # 获取完整大纲（用于上下文）
        outline = project.get("outline", [])

        # 重新生成
        new_paragraph_data = await document_generator_service.regenerate_paragraph(
            section_title=request.sectionTitle,
            section_id=request.sectionId,
            document_ids=document_ids,
            context_sections=request.contextSections if request.contextSections else None,
            custom_prompt=request.customPrompt if request.customPrompt else None,
            full_outline=outline,  # 传递完整大纲
            user_id=current_user.id,
        )

        # 如果有当前段落，保存到版本历史
        if current_paragraph:
            # 将当前段落添加到版本历史
            existing_versions.append({
                "content": current_paragraph.get("content", ""),
                "timestamp": current_paragraph.get("timestamp", ""),
                "sources": current_paragraph.get("sources", [])
            })

        # 创建新段落（包含历史版本）
        updated_paragraph = {
            "paragraph_id": new_paragraph_data.get("paragraph_id"),
            "section_id": new_paragraph_data.get("section_id"),
            "content": new_paragraph_data.get("content"),
            "sources": new_paragraph_data.get("sources", []),
            "timestamp": new_paragraph_data.get("timestamp"),
            "versions": existing_versions  # 保存所有历史版本
        }

        # 更新项目（只保留一个段落，历史在versions中）
        document_project_storage.add_section_content(
            project_id=project_id,
            section_id=request.sectionId,
            content={
                "sectionId": request.sectionId,
                "paragraphs": [updated_paragraph],  # 只保留当前段落
                "sources": updated_paragraph.get("sources", [])
            },
            user_id=current_user.id,
        )

        return updated_paragraph

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重新生成失败: {str(e)}")


@router.put("/{project_id}/paragraph")
async def update_paragraph(
    project_id: str,
    request: UpdateParagraphRequest,
    current_user: User = Depends(get_current_user),
):
    """
    更新段落内容（编辑）

    直接修改段落内容，不保存版本
    """
    try:
        updated_project = document_project_storage.update_paragraph(
            project_id=project_id,
            section_id=request.sectionId,
            paragraph_id=request.paragraphId,
            content=request.content,
            save_version=False,  # 编辑时不保存版本
            user_id=current_user.id,
        )

        if not updated_project:
            raise HTTPException(status_code=404, detail="段落不存在")

        return {"message": "更新成功"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


class RestoreParagraphVersionRequest(BaseModel):
    """恢复段落版本请求"""
    sectionId: str = Field(..., description="章节ID")
    paragraphId: str = Field(..., description="段落ID")
    versionIndex: int = Field(..., description="版本索引")


@router.post("/{project_id}/restore-paragraph-version")
async def restore_paragraph_version(
    project_id: str,
    request: RestoreParagraphVersionRequest,
    current_user: User = Depends(get_current_user),
):
    """
    恢复段落到指定版本

    将段落恢复到历史版本
    """
    try:
        updated_project = document_project_storage.restore_paragraph_version(
            project_id=project_id,
            section_id=request.sectionId,
            paragraph_id=request.paragraphId,
            version_index=request.versionIndex,
            user_id=current_user.id,
        )

        if not updated_project:
            raise HTTPException(status_code=404, detail="段落或版本不存在")

        return updated_project

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"恢复失败: {str(e)}")


@router.get("/{project_id}/export-word")
async def export_word(
    project_id: str,
    title: str = Query(default="文档", description="导出文件名"),
    current_user: User = Depends(get_current_user),
):
    """
    导出为 Word 文档

    将项目的大纲和内容导出为 Word 文档

    Args:
        project_id: 项目ID
        title: 导出文件名（不含扩展名）
    """
    try:
        project = get_owned_project_or_404(project_id, current_user.id)

        # 创建 Word 文档
        doc = Document()

        # 小四号字体 = 12磅
        font_size_small4 = Pt(12)

        # 设置文档默认样式（Normal 样式）
        style = doc.styles['Normal']
        style.font.name = 'Times New Roman'
        style.font.size = font_size_small4
        # 设置中文字体
        style._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')

        # 设置文档标题
        title = project.get("title", "文档")
        title_heading = doc.add_heading(title, 0)
        title_heading.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # 设置标题格式
        for run in title_heading.runs:
            run.font.size = font_size_small4
            run.font.bold = True
            run.font.color.rgb = RGBColor(0, 0, 0)
            run.font.underline = False
            # 使用 qn 设置字体
            run.font.name = 'Times New Roman'
            run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')

        # 移除段落边框
        try:
            pPr = title_heading._element.get_or_add_pPr()
            pBdr = pPr.find(qn('w:pBdr'))
            if pBdr is not None:
                pPr.remove(pBdr)
        except:
            pass

        # 设置标题段后间距
        title_heading.paragraph_format.line_spacing = 1.5
        title_heading.paragraph_format.space_before = Pt(0)
        title_heading.paragraph_format.space_after = Pt(0)

        # 优先使用 full_html（用户编辑后的完整内容）
        full_html = project.get("full_html", "")
        if full_html and full_html.strip():
            print(f"[DEBUG] 导出 Word: 使用 full_html，长度: {len(full_html)}")

            try:
                # 使用 BeautifulSoup 解析 HTML
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(full_html, 'html.parser')

                # 辅助函数：解析CSS样式
                def parse_style(style_str):
                    """解析CSS样式字符串为字典"""
                    styles = {}
                    if not style_str:
                        return styles
                    for item in style_str.split(';'):
                        item = item.strip()
                        if ':' in item:
                            key, value = item.split(':', 1)
                            styles[key.strip()] = value.strip()
                    return styles

                # 辅助函数：解析颜色值
                def parse_color(color_str):
                    """解析CSS颜色值，返回RGBColor对象"""
                    if not color_str:
                        return None

                    color_str = color_str.strip().lower()

                    # 处理十六进制颜色
                    if color_str.startswith('#'):
                        hex_color = color_str[1:]
                        if len(hex_color) == 3:
                            hex_color = ''.join([c*2 for c in hex_color])
                        if len(hex_color) == 6:
                            try:
                                r = int(hex_color[0:2], 16)
                                g = int(hex_color[2:4], 16)
                                b = int(hex_color[4:6], 16)
                                return RGBColor(r, g, b)
                            except:
                                pass

                    # 处理rgb()格式
                    if color_str.startswith('rgb'):
                        import re
                        match = re.search(r'rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)', color_str)
                        if match:
                            try:
                                return RGBColor(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                            except:
                                pass

                    return None

                # 辅助函数：解析字号
                def parse_font_size(size_str):
                    """解析CSS字号，返回Pt对象"""
                    if not size_str:
                        return None

                    size_str = size_str.strip().lower()

                    # 移除px单位
                    if size_str.endswith('px'):
                        try:
                            size_px = float(size_str[:-2])
                            # 像素转磅（1磅 ≈ 1.333像素）
                            return Pt(size_px / 1.333)
                        except:
                            pass

                    # 移除pt单位
                    if size_str.endswith('pt'):
                        try:
                            return Pt(float(size_str[:-2]))
                        except:
                            pass

                    return None

                # 辅助函数：从HTML元素创建带格式的runs
                def add_html_element_to_paragraph(para, element):
                    """递归处理HTML元素，保留完整格式"""
                    if element.name is None:  # 文本节点
                        text = str(element).strip()
                        if text:
                            para.add_run(text)
                    elif element.name in ['strong', 'b']:
                        run = para.add_run(element.get_text())
                        run.bold = True
                    elif element.name in ['em', 'i']:
                        run = para.add_run(element.get_text())
                        run.italic = True
                    elif element.name == 'u':
                        run = para.add_run(element.get_text())
                        run.underline = True
                    elif element.name == 's':
                        run = para.add_run(element.get_text())
                        # 删除线
                        run.font.strike = True
                    elif element.name == 'sub':
                        run = para.add_run(element.get_text())
                        run.font.subscript = True
                    elif element.name == 'sup':
                        run = para.add_run(element.get_text())
                        run.font.superscript = True
                    elif element.name == 'span':
                        # 处理内联样式
                        style_str = element.get('style', '')
                        styles = parse_style(style_str)
                        text = element.get_text()

                        if text:
                            run = para.add_run(text)

                            # 应用样式
                            if 'font-weight' in styles:
                                weight = styles['font-weight'].lower()
                                if weight in ['bold', 'bolder'] or weight.isdigit() and int(weight) >= 700:
                                    run.bold = True

                            if 'font-style' in styles:
                                if styles['font-style'].lower() == 'italic':
                                    run.italic = True

                            if 'text-decoration' in styles:
                                decoration = styles['text-decoration'].lower()
                                if 'underline' in decoration:
                                    run.underline = True
                                if 'line-through' in decoration:
                                    run.font.strike = True

                            # 颜色
                            if 'color' in styles:
                                color = parse_color(styles['color'])
                                if color:
                                    run.font.color.rgb = color

                            # 字号
                            if 'font-size' in styles:
                                size = parse_font_size(styles['font-size'])
                                if size:
                                    run.font.size = size

                            # 字体
                            if 'font-family' in styles:
                                font_name = styles['font-family'].strip('"\'')
                                run.font.name = font_name
                                # 设置中文字体
                                if any(c in font_name for c in ['宋', '黑', '楷', '仿', '微软', '雅黑']):
                                    run._element.rPr.rFonts.set(qn('w:eastAsia'), font_name)

                    elif element.name == 'br':
                        # 换行符
                        # 如果段落还没有run，先添加一个空的run
                        if not para.runs:
                            run = para.add_run('')
                        # 在最后一个run后添加换行
                        para.runs[-1].add_break()
                    elif element.name == 'img':
                        # 处理图片
                        try:
                            import io as io_module
                            import requests

                            src = element.get('src', '')
                            if src:
                                img_data = None

                                # 处理base64编码的图片
                                if src.startswith('data:image'):
                                    import base64
                                    # 解析base64图片
                                    # 格式: data:image/[type];base64,[data]
                                    if ',' in src:
                                        header, data = src.split(',', 1)
                                        img_data = base64.b64decode(data)

                                # 处理URL图片（包括相对路径和绝对路径）
                                elif src.startswith('http') or src.startswith('/'):
                                    # 如果是相对路径，尝试从请求中获取完整URL
                                    if src.startswith('/'):
                                        # 这里需要知道后端的base URL，暂时使用固定的
                                        # 实际使用时应该从项目配置中获取
                                        try:
                                            # 尝试从本地文件系统读取（如果是上传到服务器的图片）
                                            # WangEditor上传的图片通常在 static/uploads 目录
                                            import os
                                            from pathlib import Path

                                            # 移除开头的斜杠
                                            clean_src = src.lstrip('/')
                                            # 尝试在后端static目录中查找
                                            static_path = Path(__file__).parent.parent / 'static' / clean_src
                                            if static_path.exists():
                                                with open(static_path, 'rb') as f:
                                                    img_data = f.read()
                                            else:
                                                print(f"[WARNING] 图片文件不存在: {static_path}")
                                        except Exception as e:
                                            print(f"[WARNING] 读取本地图片失败: {e}")

                                    elif src.startswith('http'):
                                        # 下载网络图片
                                        try:
                                            response = requests.get(src, timeout=5)
                                            if response.status_code == 200:
                                                img_data = response.content
                                        except Exception as e:
                                            print(f"[WARNING] 下载网络图片失败: {e}")

                                # 如果成功获取图片数据，添加到Word
                                if img_data:
                                    img_stream = io_module.BytesIO(img_data)

                                    # 获取图片宽度，如果设置了的话
                                    width = element.get('width')
                                    height = element.get('height')

                                    # 添加图片（默认宽度4英寸）
                                    from docx.shared import Inches
                                    run = para.add_run()

                                    # 设置图片宽度（如果HTML中指定了宽度，尝试解析）
                                    img_width = Inches(4)  # 默认宽度
                                    if width:
                                        try:
                                            # 尝试解析宽度（可能是px或百分比）
                                            width_val = float(width.rstrip('px%'))
                                            # 像素转英寸（大约96dpi）
                                            if '%' not in width:
                                                img_width = Inches(width_val / 96)
                                        except:
                                            pass

                                    run.add_picture(img_stream, width=img_width)
                                else:
                                    # 没有获取到图片数据，添加占位符
                                    para.add_run(f'[图片: {src}]')

                        except Exception as e:
                            import traceback
                            print(f"[WARNING] 图片处理失败: {e}")
                            traceback.print_exc()
                            # 添加占位符文本
                            para.add_run('[图片]')
                    else:
                        # 递归处理子元素
                        for child in element.children:
                            add_html_element_to_paragraph(para, child)

                # 处理段落对齐方式
                def get_paragraph_alignment(element):
                    """从样式中获取段落对齐方式"""
                    style_str = element.get('style', '')
                    styles = parse_style(style_str)

                    if 'text-align' in styles:
                        align = styles['text-align'].lower()
                        if align == 'center':
                            return WD_ALIGN_PARAGRAPH.CENTER
                        elif align == 'right':
                            return WD_ALIGN_PARAGRAPH.RIGHT
                        elif align == 'justify':
                            return WD_ALIGN_PARAGRAPH.JUSTIFY
                        elif align == 'left':
                            return WD_ALIGN_PARAGRAPH.LEFT
                    # 默认使用左对齐，更符合中文文档习惯
                    return WD_ALIGN_PARAGRAPH.LEFT

                # 提取所有标题和内容
                for element in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                    tag_level = int(element.name[1])  # h1->1, h2->2, etc.
                    doc_level = min(tag_level, 9)

                    # 添加标题
                    heading = doc.add_heading(level=doc_level)

                    # 处理标题中的格式
                    add_html_element_to_paragraph(heading, element)

                    # 设置标题格式
                    for run in heading.runs:
                        if not run.font.size:
                            run.font.size = font_size_small4
                        run.font.color.rgb = RGBColor(0, 0, 0)
                        if not run.font.name or run.font.name == 'Calibri':
                            run.font.name = 'Times New Roman'
                            run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')

                    # 设置标题格式
                    heading.paragraph_format.line_spacing = 1.5
                    # 标题前后无间距，与正文保持一致
                    heading.paragraph_format.space_before = Pt(0)
                    heading.paragraph_format.space_after = Pt(0)

                    # 获取标题后的所有内容，直到下一个标题
                    content_elements = []
                    next_node = element.find_next_sibling()

                    while next_node and next_node.name not in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                        if next_node.name == 'p':
                            text = next_node.get_text(strip=True)
                            if text:
                                content_elements.append(next_node)
                        next_node = next_node.find_next_sibling()

                    # 添加内容段落（保留格式）
                    para_count = 0
                    for p_element in content_elements:
                        para = doc.add_paragraph()
                        para_count += 1

                        # 设置对齐方式
                        alignment = get_paragraph_alignment(p_element)
                        para.alignment = alignment

                        # 首行缩进和行距
                        # 首行缩进两个字符（24磅，小四号字体的两个字符宽度）
                        para.paragraph_format.first_line_indent = Pt(24)
                        para.paragraph_format.line_spacing = 1.5
                        para.paragraph_format.space_before = Pt(0)
                        # 去掉段后间距，段落之间不需要空行
                        para.paragraph_format.space_after = Pt(0)

                        # 强制设置段落格式（通过直接操作XML，确保样式不被覆盖）
                        try:
                            pPr = para._element.get_or_add_pPr()

                            # 设置首行缩进：360 twips = 24 pt
                            indent = pPr.find(qn('w:indent'))
                            if indent is None:
                                indent = OxmlElement('w:indent')
                                pPr.append(indent)
                            indent.set(qn('w:firstLine'), str(360))

                            # 设置段前段后间距为0
                            spacing = pPr.find(qn('w:spacing'))
                            if spacing is None:
                                spacing = OxmlElement('w:spacing')
                                pPr.append(spacing)
                            spacing.set(qn('w:before'), '0')
                            spacing.set(qn('w:after'), '0')
                            spacing.set(qn('w:line'), '360')  # 1.5倍行距 = 240 * 1.5 = 360 twips
                            spacing.set(qn('w:lineRule'), 'auto')

                            print(f"[DEBUG] 段落 {para_count}: XML格式已设置 - 首行缩进=360 twips, 段前段后=0, 行距=360 twips")
                        except Exception as e:
                            print(f"[WARNING] 设置段落XML格式失败: {e}")

                        # 处理段落中的格式
                        add_html_element_to_paragraph(para, p_element)

                        # 设置默认字体（只对没有设置字体的run生效）
                        for run in para.runs:
                            if not run.font.size:
                                run.font.size = font_size_small4
                            if not run.font.name or run.font.name == 'Calibri':
                                run.font.name = 'Times New Roman'
                                run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')

                        # 清理段落末尾的空白字符，避免对齐问题
                        if para.runs and len(para.runs) > 0:
                            last_run = para.runs[-1]
                            if last_run.text:
                                # 移除末尾的空白字符
                                last_run.text = last_run.text.rstrip()

                # 保存到内存
                file_stream = io.BytesIO()
                doc.save(file_stream)
                file_stream.seek(0)

                # 生成文件名
                filename = f"{title}.docx"
                encoded_filename = quote(filename)

                return StreamingResponse(
                    file_stream,
                    media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={
                        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
                    }
                )
            except Exception as e:
                import traceback
                print(f"[ERROR] 使用 full_html 导出失败: {e}")
                traceback.print_exc()
                # 如果失败，继续使用原来的方法

        # 添加大纲内容（原有逻辑）
        outline = project.get("outline", [])
        sections = project.get("sections", {})

        def add_outline_to_doc(nodes: List, doc_level: int = 1):
            """递归添加大纲节点到 Word 文档"""
            for node in nodes:
                node_id = node.get("id")
                label = node.get("label", "无标题")

                # 添加章节标题
                heading = doc.add_heading(label, level=min(doc_level, 9))

                # 设置标题格式
                for run in heading.runs:
                    run.font.size = font_size_small4
                    run.font.bold = True
                    run.font.color.rgb = RGBColor(0, 0, 0)
                    run.font.underline = False
                    # 使用 qn 设置字体
                    run.font.name = 'Times New Roman'
                    run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')

                # 移除段落边框
                try:
                    pPr = heading._element.get_or_add_pPr()
                    pBdr = pPr.find(qn('w:pBdr'))
                    if pBdr is not None:
                        pPr.remove(pBdr)
                except:
                    pass

                # 设置标题段后间距和行距
                heading.paragraph_format.line_spacing = 1.5
                heading.paragraph_format.space_before = Pt(0)
                heading.paragraph_format.space_after = Pt(0)

                # 添加章节内容（如果有）
                if node_id and node_id in sections:
                    section_data = sections[node_id]
                    paragraphs = section_data.get("paragraphs", [])

                    if paragraphs:
                        # 只显示最新段落（当前版本）
                        current_para = paragraphs[-1]

                        # 优先使用 html_content（富文本格式），如果没有则使用 content（纯文本）
                        content = current_para.get("html_content", "") or current_para.get("content", "")

                        # 如果是 HTML 格式，提取纯文本
                        if content.startswith('<') and '<' in content:
                            try:
                                from bs4 import BeautifulSoup
                                soup = BeautifulSoup(content, 'html.parser')
                                # 移除脚本和样式
                                for script in soup(["script", "style"]):
                                    script.decompose()
                                # 获取文本，用换行符分隔段落
                                text_content = soup.get_text(separator='\n\n', strip=True)
                                content = text_content
                            except:
                                # 如果 HTML 解析失败，使用简单的标签移除
                                import re
                                content = re.sub(r'<[^>]+>', '\n', content)
                                content = re.sub(r'\n\s*\n', '\n\n', content).strip()

                        # 调试：打印内容的前200个字符
                        print(f"\n[DEBUG] 导出章节: {label}")
                        print(f"[DEBUG] 内容前200字符: {repr(content[:200])}")
                        print(f"[DEBUG] 内容长度: {len(content)}")
                        print(f"[DEBUG] 包含 ** : {'**' in content}")
                        print(f"[DEBUG] 包含 * : {'*' in content}")

                        if content.strip():
                            # 直接按双换行符分割内容，每个逻辑段落单独处理
                            import re
                            paragraphs_text = re.split(r'\n\s*\n', content)

                            for para_text in paragraphs_text:
                                para_text = para_text.strip()
                                if not para_text:
                                    continue

                                # 将段落内的单换行符替换为空格，避免在Word中出现手动换行符
                                para_text = re.sub(r'\n+', ' ', para_text)

                                # 检查段落中是否包含块级公式 $$...$$
                                block_formula_pattern = r'\$\$([^\$]+?)\$\$'
                                block_formulas = list(re.finditer(block_formula_pattern, para_text, flags=re.DOTALL))

                                # 收集所有需要设置字体的段落
                                paragraphs_to_set_font = []

                                if block_formulas:
                                    # 如果包含块级公式，先分割文本和公式
                                    last_end = 0
                                    for match in block_formulas:
                                        # 添加公式前的文本（如果有）
                                        text_before = para_text[last_end:match.start()].strip()
                                        if text_before:
                                            para = doc.add_paragraph()
                                            para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                                            para.paragraph_format.first_line_indent = Pt(24)
                                            para.paragraph_format.line_spacing = 1.5
                                            para.paragraph_format.space_before = Pt(0)
                                            para.paragraph_format.space_after = Pt(0)
                                            add_markdown_to_paragraph(para, text_before)
                                            paragraphs_to_set_font.append(para)

                                        # 添加块级公式
                                        formula_latex = match.group(1).strip()
                                        from latex2word import LatexToWordElement
                                        formula_para = doc.add_paragraph()
                                        formula_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                                        formula_para.paragraph_format.space_before = Pt(0)
                                        formula_para.paragraph_format.space_after = Pt(0)
                                        formula_para.paragraph_format.line_spacing = 1.5
                                        latex_to_word = LatexToWordElement(formula_latex)
                                        latex_to_word.add_latex_to_paragraph(formula_para)
                                        # 块级公式段落不需要设置字体

                                        last_end = match.end()

                                    # 添加最后一个公式后的文本（如果有）
                                    text_after = para_text[last_end:].strip()
                                    if text_after:
                                        para = doc.add_paragraph()
                                        para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                                        para.paragraph_format.first_line_indent = Pt(24)
                                        para.paragraph_format.line_spacing = 1.5
                                        para.paragraph_format.space_before = Pt(0)
                                        para.paragraph_format.space_after = Pt(0)
                                        add_markdown_to_paragraph(para, text_after)
                                        paragraphs_to_set_font.append(para)
                                else:
                                    # 没有块级公式，直接处理整个段落
                                    para = doc.add_paragraph()

                                    # 设置段落格式
                                    para.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                                    para.paragraph_format.first_line_indent = Pt(24)  # 首行缩进
                                    para.paragraph_format.line_spacing = 1.5  # 1.5倍行距
                                    para.paragraph_format.space_before = Pt(0)
                                    para.paragraph_format.space_after = Pt(0)

                                    # 将 Markdown 内容添加到段落（保留格式）
                                    # add_markdown_to_paragraph函数内部会处理行内公式
                                    add_markdown_to_paragraph(para, para_text)
                                    paragraphs_to_set_font.append(para)

                                # 设置所有普通段落的 run 的字体（跳过已经是宋体的中文引号和代码块）
                                for para in paragraphs_to_set_font:
                                    # 跳过代码块和已经是宋体的中文引号
                                    if run.font.name == 'Courier New':
                                        continue
                                    if run.font.name == '宋体':
                                        # 中文引号已经是宋体，只需设置字体大小
                                        run.font.size = font_size_small4
                                        continue

                                    # 其他文本设置为Times New Roman
                                    run.font.size = font_size_small4
                                    run.font.name = 'Times New Roman'
                                    run._element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')

                # 递归处理子节点
                children = node.get("children", [])
                if children:
                    add_outline_to_doc(children, doc_level + 1)

        # 添加大纲内容
        if outline:
            add_outline_to_doc(outline)

        # 保存到内存
        file_stream = io.BytesIO()
        doc.save(file_stream)
        file_stream.seek(0)

        # 生成文件名（使用传递的 title 参数）
        filename = f"{title}.docx"
        encoded_filename = quote(filename)

        # 返回文件流
        return StreamingResponse(
            file_stream,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.get("/{project_id}/preview-html")
async def preview_html(
    project_id: str,
    request: Request,
    token: Optional[str] = Query(None),
):
    """
    生成HTML预览

    生成项目内容的HTML预览，用于PDF导出。
    通过 query param `token` 认证（iframe/window.open 不支持 Bearer 头）。
    """
    try:
        # 通过 query param token 认证
        if not token:
            raise HTTPException(status_code=401, detail="缺少认证 token")
        async with AsyncSessionLocal() as db:
            current_user = await get_user_by_token(token, db)

        # 获取后端基础 URL
        backend_base_url = f"{request.url.scheme}://{request.url.netloc}"

        project = get_owned_project_or_404(project_id, current_user.id)

        title = project.get("title", "文档")
        outline = project.get("outline", [])
        sections = project.get("sections", {})

        # 检查是否有 full_html
        has_full_html = False
        full_html = project.get("full_html", "")
        if full_html and full_html.strip():
            # 直接使用用户的富文本内容
            body_html = full_html
            has_full_html = True
        else:
            # 使用原有逻辑（从 sections 生成）
            body_html = ""
            has_full_html = False

        # 用于存储提取的公式
        extracted_formulas = []
        formula_counter = [0]  # 使用列表以便在嵌套函数中修改

        def protect_formulas(content: str) -> str:
            """保护 LaTeX 公式，防止被 Markdown 处理"""
            # 先提取块级公式
            content = re.sub(
                r'\$\$([^\$]+?)\$\$',
                lambda m: _extract_formula(m.group(1), 'block'),
                content,
                flags=re.DOTALL
            )
            # 再提取行内公式
            content = re.sub(
                r'\$([^\$\n]+?)\$',
                lambda m: _extract_formula(m.group(1), 'inline'),
                content
            )
            return content

        def _extract_formula(latex: str, fmt_type: str) -> str:
            """提取公式并返回占位符"""
            idx = formula_counter[0]
            formula_counter[0] += 1
            extracted_formulas.append({
                'index': idx,
                'latex': latex.strip(),
                'type': fmt_type
            })
            # 使用特殊占位符，Markdown 不会处理
            return f"MATHFORMULA{idx}PLACEHOLDER"

        # 生成HTML
        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <!-- KaTeX CSS - 先加载 KaTeX 样式 -->
    <link rel="stylesheet" href="{backend_base_url}/static/katex/katex.min.css">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        @page {{
            size: A4;
            margin: 20mm;
        }}

        html, body {{
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
        }}

        body {{
            font-family: 'Times New Roman', '宋体', serif;
            font-size: 12pt;
            line-height: 1.5;
            max-width: 210mm;
            margin: 20mm auto;
            padding: 20mm;
            background: white;
        }}

        /* 中文引号使用宋体 */
        .chinese-quote {{
            font-family: '宋体', serif;
        }}

        h1, h2, h3 {{
            font-size: 12pt;
            font-weight: bold;
            margin: 0;
            margin-top: 0;
            margin-bottom: 0;
            padding: 0;
            padding-top: 0;
            padding-bottom: 0;
            color: #000;
            line-height: 1.5;
            text-align: left;
        }}

        h1 {{
            text-align: center;
        }}

        p {{
            text-align: justify;
            text-indent: 2em;
            margin: 0;
            margin-top: 0;
            margin-bottom: 0;
            padding: 0;
            padding-top: 0;
            padding-bottom: 0;
            line-height: 1.5;
            font-size: 12pt;
            page-break-inside: avoid;
        }}

        @media print {{
            body {{
                margin: 0;
                padding: 20mm;
            }}

            h1, h2, h3, p {{
                margin: 0 !important;
                padding: 0 !important;
            }}
        }}

        /* KaTeX 公式样式 - 完全重置间距，使用最高优先级 */
        html body .katex-display,
        html body div.katex-display,
        body > .katex-display {{
            margin: 0 !important;
            padding: 0 !important;
            display: block !important;
            line-height: 1.5 !important;
        }}

        html body .katex-display > .katex,
        html body .katex {{
            line-height: 1.5 !important;
        }}

        html body .katex-display > .katex,
        html body .katex-display > .katex-display {{
            display: inline-block;
            margin: 0 !important;
            padding: 0 !important;
        }}

        /* 确保公式容器没有额外间距 */
        html body .katex-display > .katex > .katex-html,
        html body .katex-display > .katex > .katex-html > .base {{
            margin: 0 !important;
            padding: 0 !important;
        }}
    </style>
</head>
<body>
    <h1>{title}</h1>
"""

        def add_outline_html(nodes: List, level: int = 1) -> str:
            """递归生成大纲HTML"""
            html = ""
            for node in nodes:
                node_id = node.get("id")
                label = node.get("label", "无标题")

                # 根据层级选择标题标签
                if level == 1:
                    html += f"<h2>{label}</h2>"
                elif level == 2:
                    html += f"<h3>{label}</h3>"
                else:
                    html += f"<h3>{label}</h3>"

                # 添加章节内容
                if node_id and node_id in sections:
                    section_data = sections[node_id]
                    paragraphs = section_data.get("paragraphs", [])

                    if paragraphs:
                        current_para = paragraphs[-1]

                        # 优先使用 html_content（富文本格式），如果没有则使用 content（纯文本）
                        content = current_para.get("html_content", "") or current_para.get("content", "")

                        # 如果是 HTML 格式，直接使用 HTML（已经是富文本）
                        # 如果不是 HTML，继续使用 Markdown 转换
                        is_html = content.startswith('<') and '<' in content and ('<p>' in content or '<h1' in content or '<h2' in content or '<h3' in content or '<div' in content)

                        if content.strip():
                            # 如果是富文本 HTML，直接使用，不进行 Markdown 转换
                            if is_html:
                                # 直接使用 HTML 内容
                                md_html = content
                            else:
                                # 先将英文引号转换为中文引号
                                content = convert_quotes_to_chinese(content)

                                # 然后将中文引号包裹在span中（使用Unicode编码）
                                content = re.sub(
                                    r'([\u201c\u201d\u2018\u2019\u300c\u300d\u300e\u300f])',
                                    r'<span class="chinese-quote">\1</span>',
                                    content
                                )

                                # 保护 LaTeX 公式，防止被 Markdown 处理
                                content = protect_formulas(content)

                                # 将 Markdown 转换为 HTML
                                md_html = markdown.markdown(
                                    content,
                                    extensions=[
                                        'extra',          # 额外功能（表格、列表等）
                                        'nl2br',          # 换行符转 <br>
                                        'sane_lists',     # 更好的列表支持
                                    ]
                                )

                                # 将占位符替换回 LaTeX 公式（供 KaTeX auto-render 处理）
                                for formula in extracted_formulas:
                                    idx = formula['index']
                                    latex = formula['latex']
                                    fmt_type = formula['type']
                                    if fmt_type == 'block':
                                        placeholder = f"MATHFORMULA{idx}PLACEHOLDER"
                                        replacement = f"$${latex}$$"
                                    else:
                                        placeholder = f"MATHFORMULA{idx}PLACEHOLDER"
                                        replacement = f"${latex}$"
                                    md_html = md_html.replace(placeholder, replacement)

                            html += md_html

                # 递归处理子节点
                children = node.get("children", [])
                if children:
                    html += add_outline_html(children, level + 1)

            return html

        # 只有在没有 full_html 时才从 outline 生成
        if not has_full_html:
            if outline:
                body_html = add_outline_html(outline)
            else:
                body_html = ""

        html_content += body_html

        html_content += f"""    <script>
        // 动态加载 KaTeX 资源（确保加载顺序）
        (function() {{
            const backendUrl = '{backend_base_url}';

            // 加载 KaTeX 核心库
            const katexScript = document.createElement('script');
            katexScript.src = backendUrl + '/static/katex/katex.min.js';
            katexScript.onload = function() {{
                console.log('✓ KaTeX 核心库已加载');

                // KaTeX 核心库加载完成后，再加载 auto-render 插件
                const autoRenderScript = document.createElement('script');
                autoRenderScript.src = backendUrl + '/static/katex/contrib/auto-render.min.js';
                autoRenderScript.onload = function() {{
                    console.log('✓ KaTeX auto-render 已加载');

                    // auto-render 加载完成后，立即渲染公式
                    try {{
                        renderMathInElement(document.body, {{
                            delimiters: [
                                {{left: '$$', right: '$$', display: true}},
                                {{left: '$', right: '$', display: false}}
                            ],
                            throwOnError: false
                        }});
                        console.log('✓ KaTeX 公式渲染完成');
                    }} catch (e) {{
                        console.error('KaTeX 渲染失败:', e);
                    }}

                    // 渲染完成后延迟触发打印（仅当URL包含print=1参数时）
                    const urlParams = new URLSearchParams(window.location.search);
                    if (urlParams.get('print') === '1') {{
                        setTimeout(function() {{
                            window.print();
                        }}, 1000);
                    }}
                }};
                autoRenderScript.onerror = function() {{
                    console.error('✗ KaTeX auto-render 加载失败');
                }};
                document.head.appendChild(autoRenderScript);
            }};
            katexScript.onerror = function() {{
                console.error('✗ KaTeX 核心库加载失败，请检查后端静态文件服务');
            }};
            document.head.appendChild(katexScript);
        }})();
    </script>
</body>
</html>"""

        # 使用 Response 而不是 HTMLResponse，避免 Content-Length 计算错误
        return Response(
            content=html_content,
            media_type="text/html; charset=utf-8"
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"预览生成失败: {str(e)}")


class UpdateProjectContentRequest(BaseModel):
    """更新项目内容请求"""
    sections: List[dict] = Field(..., description="章节内容列表")


class UpdateFullHtmlRequest(BaseModel):
    """更新完整富文本内容请求"""
    full_html: str = Field(..., description="完整的富文本HTML内容")


@router.put("/{project_id}/full-html")
async def update_full_html(
    project_id: str,
    request: UpdateFullHtmlRequest,
    current_user: User = Depends(get_current_user),
):
    """
    更新完整的富文本内容

    直接保存编辑器的完整HTML内容
    """
    try:
        updated_project = document_project_storage.update_full_html(
            project_id=project_id,
            full_html=request.full_html,
            user_id=current_user.id,
        )

        if not updated_project:
            raise HTTPException(status_code=404, detail="项目不存在")

        return updated_project

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


@router.put("/{project_id}/content")
async def update_project_content(
    project_id: str,
    request: UpdateProjectContentRequest,
    current_user: User = Depends(get_current_user),
):
    """
    更新项目内容（富文本编辑后保存）

    更新项目的所有章节内容，用于富文本编辑器保存
    """
    try:
        project = get_owned_project_or_404(project_id, current_user.id)

        # 更新项目内容
        updated_project = document_project_storage.update_project_content(
            project_id=project_id,
            sections=request.sections,
            user_id=current_user.id,
        )

        return updated_project

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新内容失败: {str(e)}")
