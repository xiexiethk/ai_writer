"""
Word 文档直接转换为 Markdown 服务
使用 mammoth 和 markdownify，支持图片提取
"""
import os
import time
import logging
from pathlib import Path
from typing import Dict, List, Tuple
import mammoth
from markdownify import markdownify as md

logger = logging.getLogger(__name__)


class WordConverter:
    """Word 文档转换器"""

    def __init__(self, image_output_dir: str = None):
        """
        初始化转换器

        Args:
            image_output_dir: 图片输出目录，默认为 ./data/images
        """
        if image_output_dir is None:
            image_output_dir = os.path.join(os.path.dirname(__file__), "../../data/images")

        self.image_output_dir = Path(image_output_dir)
        self.image_output_dir.mkdir(parents=True, exist_ok=True)

    def convert_to_markdown(
        self,
        docx_path: str,
        base_url: str = "/api/documents/images"
    ) -> Tuple[str, List[Dict]]:
        """
        将 Word 文档转换为 Markdown

        Args:
            docx_path: Word 文档路径
            base_url: 图片的 URL 基础路径

        Returns:
            (markdown_content, images) - Markdown 内容和图片信息列表

        Raises:
            Exception: 转换失败时抛出异常
        """
        try:
            docx_path = Path(docx_path)
            if not docx_path.exists():
                raise FileNotFoundError(f"文件不存在: {docx_path}")

            logger.info(f"开始转换 Word 文档: {docx_path}")

            # 图片信息列表
            images = []

            def convert_image(image) -> Dict:
                """
                转换图片：提取并保存到本地

                Args:
                    image: mammoth 图片对象

                Returns:
                    包含 src 路径的字典
                """
                try:
                    with image.open() as image_bytes:
                        # 获取文件扩展名
                        content_type = image.content_type
                        if "/" in content_type:
                            file_suffix = content_type.split("/")[1]
                        else:
                            # 默认使用 png
                            file_suffix = "png"

                        # 生成文件名：时间戳_随机数.扩展名
                        timestamp = str(time.time()).replace(".", "")
                        file_name = f"img_{timestamp}_{hash(image_bytes.read()) % 10000}.{file_suffix}"

                        # 保存图片
                        image_path = self.image_output_dir / file_name
                        with open(image_path, 'wb') as f:
                            # 重新读取并写入
                            image_bytes.seek(0)
                            f.write(image_bytes.read())

                        # 返回相对路径
                        relative_path = f"{base_url}/{file_name}"

                        logger.info(f"图片已保存: {file_name}")

                        images.append({
                            "filename": file_name,
                            "local_path": str(image_path),
                            "url_path": relative_path
                        })

                        return {"src": relative_path}

                except Exception as e:
                    logger.error(f"图片转换失败: {e}")
                    # 返回占位符
                    return {"src": ""}

            # 读取 Word 文档
            with open(docx_path, "rb") as docx_file:
                # 转换为 HTML（带图片提取）
                result = mammoth.convert_to_html(
                    docx_file,
                    convert_image=mammoth.images.img_element(convert_image)
                )

                html = result.value

                # 检查转换消息
                if result.messages:
                    for msg in result.messages:
                        logger.info(f"转换消息: {msg}")

            # 将 HTML 转换为 Markdown
            markdown_content = md(html, heading_style="ATX")

            logger.info(f"转换完成，提取了 {len(images)} 张图片")

            return markdown_content, images

        except Exception as e:
            logger.error(f"Word 转 Markdown 失败: {e}")
            raise

    def convert_to_markdown_simple(
        self,
        docx_path: str
    ) -> str:
        """
        简单转换（不处理图片）

        Args:
            docx_path: Word 文档路径

        Returns:
            Markdown 内容
        """
        try:
            with open(docx_path, "rb") as docx_file:
                result = mammoth.convert_to_markdown(docx_file)
                return result.value
        except Exception as e:
            logger.error(f"Word 转 Markdown 失败: {e}")
            raise


# 全局转换器实例
word_converter = WordConverter()
