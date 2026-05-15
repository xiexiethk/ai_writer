#!/usr/bin/env python3
"""
MinerU 在线 API 解析器
使用 MinerU 在线 API 替代本地 MinerU 环境
"""
import sys
import os
import json
import argparse
import time
from pathlib import Path

from app.core.network import create_httpx_client

MINERU_API_BASE = "https://mineru.net/api/v4"
API_TOKEN = os.environ.get("MINERU_API_TOKEN", "")


def create_headers() -> dict:
    return {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
    }


def submit_task(pdf_url: str, lang: str = "ch", data_id: str = "") -> str:
    """
    提交 PDF 解析任务到 MinerU API。

    Args:
        pdf_url: PDF 下载 URL
        lang: 语言
        data_id: 自定义数据 ID

    Returns:
        task_id: 任务 ID
    """
    payload = {
        "url": pdf_url,
        "lang": lang,
        "data_id": data_id,
        "is_ocr": True,
        "enable_formula": True,
        "enable_table": True,
    }

    with create_httpx_client(timeout=30.0) as client:
        response = client.post(
            f"{MINERU_API_BASE}/extract/task",
            json=payload,
            headers=create_headers(),
        )
        response.raise_for_status()
        result = response.json()
        task_id = result.get("data", {}).get("task_id")
        if not task_id:
            raise ValueError(f"MinerU API 提交失败: {result}")
        return task_id


def poll_task(task_id: str, max_retries: int = 120, interval: float = 5.0) -> dict:
    """
    轮询任务状态直至完成。

    Args:
        task_id: 任务 ID
        max_retries: 最大重试次数
        interval: 轮询间隔（秒）

    Returns:
        解析结果
    """
    for attempt in range(max_retries):
        with create_httpx_client(timeout=30.0) as client:
            response = client.get(
                f"{MINERU_API_BASE}/extract/task/{task_id}",
                headers=create_headers(),
            )
            response.raise_for_status()
            result = response.json()
            state = result.get("data", {}).get("state")
            if state == "done":
                return result.get("data", {})
            elif state == "failed":
                error = result.get("data", {}).get("error", "未知错误")
                raise RuntimeError(f"MinerU 解析失败: {error}")
            # else: "running" or "waiting" — keep polling
        time.sleep(interval)

    raise TimeoutError(f"MinerU 解析超时（{max_retries * interval} 秒后仍未完成）")


def get_result_content(data: dict) -> dict:
    """
    从完成的数据中提取 Markdown 内容和图片列表。

    Args:
        data: 任务完成后的数据

    Returns:
        dict: {markdown_content: str, images: list, full_content: dict}
    """
    markdown_content = data.get("extract_result", {}).get("markdown", "") or ""
    images_raw = data.get("extract_result", {}).get("images", []) or []
    images = [img.get("name", "") for img in images_raw if img.get("name")]
    return {
        "markdown_content": markdown_content,
        "images": images,
        "full_content": data,
    }


def parse_pdf(pdf_path: str, output_dir: str, backend: str = "api", lang: str = "ch"):
    """
    使用 MinerU API 解析 PDF 文件。

    Args:
        pdf_path: PDF 文件路径（本地路径）
        output_dir: 输出目录
        backend: 后端（固定为 "api"）
        lang: 语言

    Returns:
        dict: 解析结果 {success: bool, markdown_content: str, images: list, error: str}
    """
    try:
        from app.core.config import settings
        api_token = settings.MINERU_API_TOKEN
    except Exception:
        api_token = os.environ.get("MINERU_API_TOKEN", "")

    if not api_token:
        return {
            "success": False,
            "error": "未设置 MINERU_API_TOKEN，请在 .env 中配置或设置环境变量",
            "markdown_content": "",
            "images": [],
        }

    global API_TOKEN
    API_TOKEN = api_token

    try:
        # 上传 PDF 文件（或生成可访问的 URL）
        # 对于本地文件，我们需要先生成一个可访问的 URL
        # 这里使用文件上传方式
        pdf_path_obj = Path(pdf_path)
        if not pdf_path_obj.exists():
            return {
                "success": False,
                "error": f"PDF 文件不存在: {pdf_path}",
                "markdown_content": "",
                "images": [],
            }

        # 使用 MinerU 的文件上传 API
        with create_httpx_client(timeout=120.0) as client:
            with open(pdf_path, "rb") as f:
                upload_response = client.post(
                    f"{MINERU_API_BASE}/extract/upload",
                    files={"file": (pdf_path_obj.name, f, "application/pdf")},
                    headers={"Authorization": f"Bearer {API_TOKEN}"},
                )
            upload_response.raise_for_status()
            upload_data = upload_response.json()
            pdf_url = upload_data.get("data", {}).get("url")
            data_id = upload_data.get("data", {}).get("data_id", pdf_path_obj.stem)

        if not pdf_url:
            return {
                "success": False,
                "error": f"MinerU 文件上传失败: {upload_data}",
                "markdown_content": "",
                "images": [],
            }

        # 提交解析任务
        task_id = submit_task(pdf_url, lang=lang, data_id=data_id)
        print(f"任务已提交: {task_id}")

        # 轮询结果
        result_data = poll_task(task_id)

        # 提取内容
        content = get_result_content(result_data)

        return {
            "success": True,
            "markdown_content": content["markdown_content"],
            "images": content["images"],
            "error": None,
        }

    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
            "markdown_content": "",
            "images": [],
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MinerU PDF 解析器（在线 API）")
    parser.add_argument("--pdf-path", required=True, help="PDF 文件路径")
    parser.add_argument("--output-dir", required=True, help="输出目录")
    parser.add_argument("--backend", default="api", help="MinerU 后端")
    parser.add_argument("--lang", default="ch", help="语言")

    args = parser.parse_args()

    result = parse_pdf(
        pdf_path=args.pdf_path,
        output_dir=args.output_dir,
        backend=args.backend,
        lang=args.lang,
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["success"] else 1)
