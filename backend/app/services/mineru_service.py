"""
MinerU 文档解析服务 - 使用在线 API
不再需要本地 MinerU 环境或 GPU
"""
import os
import asyncio
from pathlib import Path
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.core.network import create_async_httpx_client


class MinerUService:
    """MinerU 解析服务 - 使用在线 API，无需本地环境"""

    def __init__(self):
        self.output_dir = settings.MINERU_OUTPUT_DIR
        self.api_token = settings.MINERU_API_TOKEN
        self.api_base = "https://mineru.net/api/v4"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_token}",
        }

    @staticmethod
    def _extract_text_with_pypdf(pdf_path: str) -> Optional[str]:
        """快速回退：对可直接抽文本的 PDF，用 pypdf 提取纯文本。"""
        try:
            from pypdf import PdfReader
            reader = PdfReader(pdf_path)
            texts = []
            for page in reader.pages:
                text = (page.extract_text() or "").strip()
                if text:
                    texts.append(text)
            content = "\n\n".join(texts).strip()
            return content or None
        except Exception as exc:
            logger.warning("pypdf 文本抽取失败: %s", exc)
            return None

    async def parse_pdf(
        self, pdf_path: str, document_id: str
    ) -> Tuple[Optional[str], Optional[str], Optional[list]]:
        """
        使用 MinerU 在线 API 解析 PDF 文件。

        流程：
        1. 上传 PDF 文件到 MinerU
        2. 提交解析任务
        3. 轮询等待结果
        4. 返回 Markdown 内容和图片列表
        """
        pdf_path_obj = Path(pdf_path)
        if not pdf_path_obj.exists():
            error_msg = f"PDF 文件不存在: {pdf_path}"
            logger.error(error_msg)
            return None, error_msg, []

        os.makedirs(self.output_dir, exist_ok=True)

        try:
            # MinerU v4 API 仅接受 URL，不支持文件上传
            # 改用 Agent API (v1) 支持文件上传
            logger.info("上传 PDF 文件到 MinerU Agent API: %s", pdf_path)
            async with create_async_httpx_client(timeout=120.0) as client:
                with open(pdf_path, "rb") as f:
                    upload_response = await client.post(
                        f"{self.api_base}/../v1/agent/parse/file",
                        files={"file": (pdf_path_obj.name, f, "application/pdf")},
                        headers={"Authorization": self._headers()["Authorization"]},
                    )
                upload_response.raise_for_status()
                upload_data = upload_response.json()
                task_id = upload_data.get("data", {}).get("task_id")
                data_id = upload_data.get("data", {}).get("data_id", pdf_path_obj.stem)

            if not task_id:
                error_msg = f"文件上传失败: {upload_data}"
                logger.error(error_msg)
                fallback = self._extract_text_with_pypdf(pdf_path)
                if fallback:
                    return fallback, None, []
                return None, error_msg, []

            # Step 2: 等待 Agent API 结果（v1 是同步的）
            logger.info("等待 MinerU Agent 解析结果...")
            await asyncio.sleep(3)  # 等3秒让解析开始
            for attempt in range(120):
                await asyncio.sleep(5)
                async with create_async_httpx_client(timeout=30.0) as client:
                    poll_response = await client.get(
                        f"{self.api_base}/../v1/agent/parse/task/{task_id}",
                        headers=self._headers(),
                    )
                    poll_response.raise_for_status()
                    poll_result = poll_response.json()
                    state = poll_result.get("data", {}).get("state")

                    if state == "done":
                        result_data = poll_result.get("data", {})
                        break
                    elif state == "failed":
                        error = poll_result.get("data", {}).get("error", "未知错误")
                        logger.error("MinerU 解析失败: %s", error)
                        fallback = self._extract_text_with_pypdf(pdf_path)
                        if fallback:
                            return fallback, None, []
                        return None, error, []

                if attempt % 6 == 0:  # 每 30 秒打印一次状态
                    logger.info("MinerU 解析中... (attempt %d/%d)", attempt + 1, max_retries)

            if result_data is None:
                error_msg = f"MinerU 解析超时（{max_retries * interval} 秒后仍未完成）"
                logger.error(error_msg)
                fallback = self._extract_text_with_pypdf(pdf_path)
                if fallback:
                    return fallback, None, []
                return None, error_msg, []

            # Step 4: 提取结果
            markdown_content = result_data.get("extract_result", {}).get("markdown", "") or ""
            images_raw = result_data.get("extract_result", {}).get("images", []) or []
            images = [img.get("name", "") for img in images_raw if img.get("name")]

            # 保存 Markdown 到本地
            output_path = Path(self.output_dir) / pdf_path_obj.stem
            output_path.mkdir(parents=True, exist_ok=True)
            md_file = output_path / f"{pdf_path_obj.stem}.md"
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(markdown_content)

            logger.info(f"PDF 解析完成: {pdf_path}, Markdown 长度: {len(markdown_content)}, 图片数: {len(images)}")
            return markdown_content, None, images

        except Exception as e:
            logger.error(f"PDF 解析失败: {e}", exc_info=True)
            fallback = self._extract_text_with_pypdf(pdf_path)
            if fallback:
                logger.warning("MinerU API 异常，已回退到 pypdf 纯文本抽取: %s", pdf_path)
                return fallback, None, []
            return None, str(e), []


# 全局服务实例
mineru_service = MinerUService()
