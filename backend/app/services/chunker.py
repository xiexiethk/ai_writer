"""
Markdown 文档分块服务
基于标题层级和内容进行智能分块
"""
import re
from typing import List, Dict, Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class Chunk:
    """文档块"""
    id: str
    content: str
    title: str
    level: int  # 标题层级（0=文档根，1=#，2=##，3=###）
    chunk_index: int  # 块在文档中的索引
    metadata: Dict


class MarkdownChunker:
    """Markdown 文档分块器"""

    def __init__(
        self,
        max_chunk_size: int = 1000,  # 最大块大小（字符数）
        chunk_overlap: int = 100,     # 块之间的重叠字符数
        min_chunk_size: int = 100,    # 最小块大小
        allow_oversize: float = 0.2   # 允许超出最大块大小的比例（20%）
    ):
        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.allow_oversize = allow_oversize

    def chunk(self, markdown_content: str, doc_id: str) -> List[Chunk]:
        """
        对 Markdown 文档进行分块

        Args:
            markdown_content: Markdown 文档内容
            doc_id: 文档 ID

        Returns:
            分块列表
        """
        lines = markdown_content.split('\n')
        chunks = []
        current_section = {"title": "文档开头", "level": 0, "content": [], "index": 0}

        for line in lines:
            # 检查是否是标题
            header_match = re.match(r'^(#{1,6})\s+(.+)$', line)

            if header_match:
                # 保存当前章节（只有当有内容时才保存）
                if current_section["content"]:
                    section_chunks = self._split_section(current_section, doc_id)
                    chunks.extend(section_chunks)

                # 开始新章节
                level = len(header_match.group(1))
                title = header_match.group(2).strip()
                current_section = {
                    "title": title,
                    "level": level,
                    "content": [],
                    "index": len(chunks)
                }
            else:
                # 添加到当前章节
                current_section["content"].append(line)

        # 处理最后一个章节（只有当有内容时才保存）
        if current_section["content"]:
            section_chunks = self._split_section(current_section, doc_id)
            chunks.extend(section_chunks)

        # 如果没有任何chunk（文档完全是空的），至少创建一个
        if not chunks:
            chunks.append(Chunk(
                id=f"{doc_id}_chunk_0",
                content=markdown_content.strip(),
                title="文档内容",
                level=0,
                chunk_index=0,
                metadata={}
            ))

        logger.info(f"文档分块完成：共 {len(chunks)} 个块")
        return chunks

    def _ensure_sentence_boundary(self, text: str) -> str:
        """
        确保文本以完整句子结束

        Args:
            text: 输入文本

        Returns:
            以完整句子结束的文本（如果可能）
        """
        # 从后向前查找句子结束符
        sentence_endings = ('。', '！', '？', '.', '!', '?', '》', '"', "'", '）', ')', '】', ']')

        # 从末尾开始查找，但至少保留min_chunk_size的内容
        min_search = max(self.min_chunk_size, len(text) // 2)

        for i in range(len(text) - 1, min_search - 1, -1):
            if text[i] in sentence_endings:
                # 找到句子边界，截断到这里
                return text[:i + 1]

        # 如果找不到句子边界，尝试在标点符号处分割
        secondary_marks = ('，', '、', ',', ';', '；', '：', ':', '（', '(', '【', '[')
        for i in range(len(text) - 1, min_search - 1, -1):
            if text[i] in secondary_marks:
                return text[:i + 1]

        # 实在找不到，返回原文本
        return text

    def _split_section(self, section: Dict, doc_id: str) -> List[Chunk]:
        """
        将章节内容分割成合适的块

        Args:
            section: 章节信息
            doc_id: 文档 ID

        Returns:
            块列表
        """
        content_text = '\n'.join(section["content"])
        title = section["title"]
        level = section["level"]
        start_index = section["index"]

        # 去除首尾空白
        content_text = content_text.strip()

        # 如果内容为空，返回空列表
        if not content_text:
            return []

        if len(content_text) <= self.max_chunk_size:
            # 内容小于最大块大小，直接作为一个块
            return [
                Chunk(
                    id=f"{doc_id}_chunk_{start_index}",
                    content=content_text,
                    title=title,
                    level=level,
                    chunk_index=start_index,
                    metadata={
                        "type": "section",
                        "start_char": 0,
                        "end_char": len(content_text)
                    }
                )
            ]

        # 内容过长，需要分割
        chunks = []
        paragraphs = re.split(r'\n\n+', content_text.strip())
        current_chunk = ""
        chunk_count = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # 如果当前段落本身就很长，需要强制分割
            if len(para) > self.max_chunk_size:
                # 先保存当前块
                if current_chunk:
                    chunks.append(self._create_chunk(
                        doc_id, current_chunk, title, level,
                        start_index + chunk_count
                    ))
                    chunk_count += 1

                # 分割长段落
                para_chunks = self._split_long_paragraph(para)
                for i, para_chunk in enumerate(para_chunks):
                    chunks.append(self._create_chunk(
                        doc_id, para_chunk, title, level,
                        start_index + chunk_count
                    ))
                    chunk_count += 1

                current_chunk = ""
            else:
                # 检查添加这个段落是否会超过最大块大小
                potential_length = len(current_chunk) + len(para) + 2

                if potential_length <= self.max_chunk_size:
                    # 可以完整添加这个段落
                    if current_chunk and self.chunk_overlap > 0:
                        overlap_text = current_chunk[-self.chunk_overlap:]
                        current_chunk = overlap_text + "\n\n" + para
                    else:
                        current_chunk = para if not current_chunk else current_chunk + "\n\n" + para
                else:
                    # 会超出限制，检查是否可以略微超出以包含完整句子
                    max_allowed = int(self.max_chunk_size * (1 + self.allow_oversize))

                    if potential_length <= max_allowed:
                        # 允许略微超出，直接添加
                        current_chunk = para if not current_chunk else current_chunk + "\n\n" + para

                        # 保存当前块（确保以完整句子结束）
                        if current_chunk:
                            adjusted_chunk = self._ensure_sentence_boundary(current_chunk)
                            chunks.append(self._create_chunk(
                                doc_id, adjusted_chunk, title, level,
                                start_index + chunk_count
                            ))
                            chunk_count += 1

                            # 保存被截断的部分作为下一块的开始
                            remaining = current_chunk[len(adjusted_chunk):].strip()
                            current_chunk = remaining if remaining else ""
                        else:
                            current_chunk = ""
                    else:
                        # 超出太多，必须分割
                        if current_chunk:
                            # 确保当前块以完整句子结束
                            adjusted_chunk = self._ensure_sentence_boundary(current_chunk)
                            chunks.append(self._create_chunk(
                                doc_id, adjusted_chunk, title, level,
                                start_index + chunk_count
                            ))
                            chunk_count += 1

                            # 保存被截断的部分
                            remaining = current_chunk[len(adjusted_chunk):].strip()
                            current_chunk = remaining + "\n\n" + para if remaining else para
                        else:
                            current_chunk = para

        # 处理最后一个块
        if current_chunk:
            # 确保最后一个块也以完整句子结束
            adjusted_chunk = self._ensure_sentence_boundary(current_chunk)
            chunks.append(self._create_chunk(
                doc_id, adjusted_chunk, title, level,
                start_index + chunk_count
            ))

            # 保存被截断的部分（如果有）
            remaining = current_chunk[len(adjusted_chunk):].strip()
            if remaining:
                chunks.append(self._create_chunk(
                    doc_id, remaining, title, level,
                    start_index + chunk_count + 1
                ))

        return chunks

    def _split_long_paragraph(self, paragraph: str) -> List[str]:
        """
        分割过长的段落

        Args:
            paragraph: 段落文本

        Returns:
            分割后的文本列表
        """
        chunks = []
        start = 0

        while start < len(paragraph):
            end = start + self.max_chunk_size

            # 尝试在句子边界分割
            if end < len(paragraph):
                # 寻找最近的句号、问号或感叹号
                for i in range(end, max(start + self.min_chunk_size, start), -1):
                    if paragraph[i] in '。！？.!?':
                        end = i + 1
                        break
                else:
                    # 如果找不到句子边界，在空格处分割
                    for i in range(end, max(start + self.min_chunk_size, start), -1):
                        if paragraph[i] in ' \t':
                            end = i + 1
                            break

            chunk = paragraph[start:end].strip()
            if chunk:
                chunks.append(chunk)

            # 添加重叠
            start = end - self.chunk_overlap if end < len(paragraph) else end

        return chunks

    def _create_chunk(
        self,
        doc_id: str,
        content: str,
        title: str,
        level: int,
        chunk_index: int
    ) -> Chunk:
        """创建块对象"""
        return Chunk(
            id=f"{doc_id}_chunk_{chunk_index}",
            content=content,
            title=title,
            level=level,
            chunk_index=chunk_index,
            metadata={
                "type": "chunk",
                "start_char": 0,
                "end_char": len(content)
            }
        )


# 全局分块器实例
chunker = MarkdownChunker()
