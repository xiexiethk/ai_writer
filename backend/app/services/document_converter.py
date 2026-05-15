"""
文档格式转换服务
支持将各种格式文档转换为 PDF
"""
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple
import logging

from PIL import Image
import img2pdf

logger = logging.getLogger(__name__)


class DocumentConverter:
    """文档转换器"""

    def __init__(self):
        # LibreOffice 路径配置
        self.libreoffice_paths = [
            "libreoffice",
            "soffice",
            "/usr/bin/libreoffice",
            "/usr/bin/soffice",
            "/Applications/LibreOffice.app/Contents/MacOS/soffice",
            "C:\\Program Files\\LibreOffice\\program\\soffice.exe",
        ]
        self.libreoffice_cmd = self._find_libreoffice()

    def _find_libreoffice(self) -> Optional[str]:
        """查找 LibreOffice 可执行文件"""
        for cmd in self.libreoffice_paths:
            try:
                result = subprocess.run(
                    [cmd, "--version"],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0:
                    logger.info(f"找到 LibreOffice: {cmd}")
                    return cmd
            except (subprocess.SubprocessError, FileNotFoundError):
                continue

        logger.warning("未找到 LibreOffice，Office 文档转换功能将不可用")
        return None

    def convert_to_pdf(
        self,
        file_path: str,
        output_dir: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        将文档转换为 PDF

        Args:
            file_path: 原文件路径
            output_dir: 输出目录，如果为 None 则使用原文件所在目录

        Returns:
            (pdf_file_path, converted_extension) - PDF 文件路径和转换后的扩展名

        Raises:
            Exception: 转换失败时抛出异常
        """
        file_path = Path(file_path)
        file_ext = file_path.suffix.lower()

        # 如果已经是 PDF，直接返回
        if file_ext == ".pdf":
            return str(file_path), file_ext

        # 确保输出目录存在
        if output_dir is None:
            output_dir = file_path.parent
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        # 根据文件类型选择转换方法
        if file_ext in [".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp"]:
            return self._convert_office_to_pdf(file_path, output_dir)
        elif file_ext in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff"]:
            return self._convert_image_to_pdf(file_path, output_dir)
        elif file_ext == ".txt":
            return self._convert_txt_to_pdf(file_path, output_dir)
        elif file_ext in [".html", ".htm"]:
            return self._convert_html_to_pdf(file_path, output_dir)
        elif file_ext == ".md":
            return self._convert_markdown_to_pdf(file_path, output_dir)
        else:
            raise ValueError(f"不支持的文件格式: {file_ext}")

    def _convert_office_to_pdf(
        self,
        file_path: Path,
        output_dir: Path
    ) -> Tuple[str, str]:
        """
        使用 LibreOffice 转换 Office 文档为 PDF

        Args:
            file_path: Office 文件路径
            output_dir: 输出目录

        Returns:
            (pdf_file_path, ".pdf")
        """
        if not self.libreoffice_cmd:
            raise RuntimeError(
                "LibreOffice 未安装，无法转换 Office 文档。"
                "请安装 LibreOffice: sudo apt-get install libreoffice"
            )

        try:
            # 使用 LibreOffice 转换
            # --headless: 无界面模式
            # --convert-to pdf: 转换为 PDF
            # --outdir: 输出目录
            result = subprocess.run(
                [
                    self.libreoffice_cmd,
                    "--headless",
                    "--convert-to", "pdf",
                    "--outdir", str(output_dir),
                    str(file_path)
                ],
                capture_output=True,
                text=True,
                timeout=60  # 60 秒超时
            )

            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "未知错误"
                raise RuntimeError(f"LibreOffice 转换失败: {error_msg}")

            # 查找生成的 PDF 文件
            pdf_path = output_dir / f"{file_path.stem}.pdf"

            if not pdf_path.exists():
                raise RuntimeError(f"PDF 文件未生成: {pdf_path}")

            logger.info(f"Office 文档转换成功: {file_path} -> {pdf_path}")
            return str(pdf_path), ".pdf"

        except subprocess.TimeoutExpired:
            raise RuntimeError("LibreOffice 转换超时（60秒）")
        except Exception as e:
            logger.error(f"Office 文档转换失败: {e}")
            raise

    def _convert_image_to_pdf(
        self,
        file_path: Path,
        output_dir: Path
    ) -> Tuple[str, str]:
        """
        将图片转换为 PDF

        Args:
            file_path: 图片文件路径
            output_dir: 输出目录

        Returns:
            (pdf_file_path, ".pdf")
        """
        try:
            pdf_path = output_dir / f"{file_path.stem}.pdf"

            # 使用 img2pdf 转换（高质量，适合文档）
            with open(file_path, "rb") as img_file:
                pdf_bytes = img2pdf.convert(img_file)

            with open(pdf_path, "wb") as pdf_file:
                pdf_file.write(pdf_bytes)

            logger.info(f"图片转换成功: {file_path} -> {pdf_path}")
            return str(pdf_path), ".pdf"

        except Exception as e:
            logger.error(f"图片转换失败: {e}")
            # 降级方案：使用 PIL
            try:
                return self._convert_image_to_pdf_pil(file_path, output_dir)
            except Exception as e2:
                raise RuntimeError(f"图片转换失败: {e}, 降级方案也失败: {e2}")

    def _convert_image_to_pdf_pil(
        self,
        file_path: Path,
        output_dir: Path
    ) -> Tuple[str, str]:
        """
        使用 PIL 将图片转换为 PDF（降级方案）

        Args:
            file_path: 图片文件路径
            output_dir: 输出目录

        Returns:
            (pdf_file_path, ".pdf")
        """
        try:
            pdf_path = output_dir / f"{file_path.stem}.pdf"

            # 打开图片
            image = Image.open(file_path)

            # 如果是 RGBA 模式，转换为 RGB
            if image.mode == "RGBA":
                image = image.convert("RGB")

            # 保存为 PDF
            image.save(pdf_path, "PDF", resolution=150.0)

            logger.info(f"图片转换成功（PIL）: {file_path} -> {pdf_path}")
            return str(pdf_path), ".pdf"

        except Exception as e:
            logger.error(f"图片转换失败（PIL）: {e}")
            raise

    def _convert_txt_to_pdf(
        self,
        file_path: Path,
        output_dir: Path
    ) -> Tuple[str, str]:
        """
        将 TXT 文件转换为 PDF

        Args:
            file_path: TXT 文件路径
            output_dir: 输出目录

        Returns:
            (pdf_file_path, ".pdf")
        """
        try:
            from reportlab.lib.pagesizes import letter, A4
            from reportlab.lib.units import inch
            from reportlab.pdfgen import canvas
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import SimpleDocTemplate, Paragraph, PageBreak
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            import textwrap

            pdf_path = output_dir / f"{file_path.stem}.pdf"

            # 读取文本内容
            with open(file_path, "r", encoding="utf-8") as f:
                text_content = f.read()

            # 创建 PDF
            doc = SimpleDocTemplate(
                str(pdf_path),
                pagesize=A4,
                leftMargin=1*inch,
                rightMargin=1*inch,
                topMargin=1*inch,
                bottomMargin=1*inch,
            )

            # 样式
            styles = getSampleStyleSheet()
            style_normal = styles["Normal"]
            style_normal.fontName = "Helvetica"
            style_normal.fontSize = 11
            style_normal.leading = 14

            # 分割文本为段落
            paragraphs = []
            for line in text_content.split("\n"):
                if line.strip():  # 跳过空行
                    # 长行自动换行
                    wrapped_lines = textwrap.wrap(line, width=90)
                    for wrapped_line in wrapped_lines:
                        paragraphs.append(Paragraph(wrapped_line, style_normal))
                else:
                    # 空行添加一个空段落
                    paragraphs.append(Paragraph("<br/>", style_normal))

            # 构建 PDF
            doc.build(paragraphs)

            logger.info(f"TXT 文件转换成功: {file_path} -> {pdf_path}")
            return str(pdf_path), ".pdf"

        except ImportError:
            raise RuntimeError(
                "reportlab 未安装，无法转换 TXT 文件。"
                "请安装: pip install reportlab"
            )
        except Exception as e:
            logger.error(f"TXT 文件转换失败: {e}")
            raise

    def _convert_html_to_pdf(
        self,
        file_path: Path,
        output_dir: Path
    ) -> Tuple[str, str]:
        """
        将 HTML 文件转换为 PDF

        Args:
            file_path: HTML 文件路径
            output_dir: 输出目录

        Returns:
            (pdf_file_path, ".pdf")
        """
        try:
            # 尝试使用 pdfkit
            import pdfkit

            pdf_path = output_dir / f"{file_path.stem}.pdf"

            options = {
                'quiet': '',
                'page-size': 'A4',
                'margin-top': '0.75in',
                'margin-right': '0.75in',
                'margin-bottom': '0.75in',
                'margin-left': '0.75in',
                'encoding': 'UTF-8',
                'no-outline': None
            }

            pdfkit.from_file(str(file_path), str(pdf_path), options=options)

            logger.info(f"HTML 文件转换成功: {file_path} -> {pdf_path}")
            return str(pdf_path), ".pdf"

        except ImportError:
            # 降级方案：使用 wkhtmltopdf 命令
            try:
                pdf_path = output_dir / f"{file_path.stem}.pdf"

                result = subprocess.run(
                    ["wkhtmltopdf", str(file_path), str(pdf_path)],
                    capture_output=True,
                    timeout=30
                )

                if result.returncode != 0:
                    raise RuntimeError(f"wkhtmltopdf 转换失败: {result.stderr.decode()}")

                logger.info(f"HTML 文件转换成功（wkhtmltopdf）: {file_path} -> {pdf_path}")
                return str(pdf_path), ".pdf"

            except FileNotFoundError:
                raise RuntimeError(
                    "HTML 转 PDF 需要安装 pdfkit 或 wkhtmltopdf。"
                    "请安装: pip install pdfkit 或 sudo apt-get install wkhtmltopdf"
                )
        except Exception as e:
            logger.error(f"HTML 文件转换失败: {e}")
            raise

    def _convert_markdown_to_pdf(
        self,
        file_path: Path,
        output_dir: Path
    ) -> Tuple[str, str]:
        """
        将 Markdown 文件转换为 PDF

        策略：
        1. 先将 Markdown 转换为 HTML
        2. 再将 HTML 转换为 PDF

        Args:
            file_path: Markdown 文件路径
            output_dir: 输出目录

        Returns:
            (pdf_file_path, ".pdf")
        """
        try:
            import markdown

            # 读取 Markdown 内容
            with open(file_path, "r", encoding="utf-8") as f:
                md_content = f.read()

            # 转换为 HTML
            html_content = markdown.markdown(
                md_content,
                extensions=['tables', 'fenced_code', 'nl2br', 'sane_lists']
            )

            # 创建完整的 HTML 文档
            full_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 40px; }}
                    h1, h2, h3, h4, h5, h6 {{ margin-top: 24px; margin-bottom: 16px; font-weight: 600; }}
                    h1 {{ font-size: 2em; border-bottom: 1px solid #eee; padding-bottom: 0.3em; }}
                    h2 {{ font-size: 1.5em; border-bottom: 1px solid #eee; padding-bottom: 0.3em; }}
                    h3 {{ font-size: 1.25em; }}
                    code {{ background-color: #f6f8fa; padding: 0.2em 0.4em; border-radius: 3px; font-family: monospace; }}
                    pre {{ background-color: #f6f8fa; padding: 16px; border-radius: 6px; overflow: auto; }}
                    pre code {{ background-color: transparent; padding: 0; }}
                    table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
                    th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
                    th {{ background-color: #f2f2f2; }}
                    blockquote {{ border-left: 4px solid #ddd; padding-left: 16px; color: #666; margin: 16px 0; }}
                    img {{ max-width: 100%; height: auto; }}
                </style>
            </head>
            <body>
                {html_content}
            </body>
            </html>
            """

            # 保存临时 HTML 文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
                temp_html = f.name
                f.write(full_html)

            try:
                # 转换 HTML 为 PDF
                pdf_path, _ = self._convert_html_to_pdf(Path(temp_html), output_dir)
                logger.info(f"Markdown 文件转换成功: {file_path} -> {pdf_path}")
                return pdf_path, ".pdf"
            finally:
                # 删除临时 HTML 文件
                try:
                    os.unlink(temp_html)
                except:
                    pass

        except ImportError:
            raise RuntimeError(
                "markdown 库未安装，无法转换 Markdown 文件。"
                "请安装: pip install markdown"
            )
        except Exception as e:
            logger.error(f"Markdown 文件转换失败: {e}")
            raise

    def is_supported_format(self, file_ext: str) -> bool:
        """
        检查文件格式是否支持转换

        Args:
            file_ext: 文件扩展名（带点号或不带点号）

        Returns:
            是否支持转换
        """
        # 标准化扩展名
        if not file_ext.startswith("."):
            file_ext = "." + file_ext
        file_ext = file_ext.lower()

        supported_formats = [
            ".pdf",
            # Office 文档
            ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
            ".odt", ".ods", ".odp",
            # 图片
            ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff",
            # 文本
            ".txt",
            # 网页
            ".html", ".htm",
            # Markdown
            ".md",
        ]

        return file_ext in supported_formats


# 全局转换器实例
document_converter = DocumentConverter()
