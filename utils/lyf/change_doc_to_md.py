import os
from pathlib import Path
import mammoth
import sys

# 添加父目录到 sys.path 以导入 server_config
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import server_config

def convert_docx_dir_to_md(type,folder_name):
    root_path = server_config.REPORT_DIR
    dir_path = os.path.join(root_path, type, folder_name)
    """
    将指定目录下的所有 docx 文件逐一转换为 Markdown，
    并将 md 文件与图片输出到同一目录中。

    :param dir_path: 包含 docx 文件的目录路径
    """
    base_dir = Path(dir_path)
    if not base_dir.exists() or not base_dir.is_dir():
        raise ValueError(f"非法目录路径: {dir_path}")

    image_dir = base_dir / "images"
    image_dir.mkdir(exist_ok=True)

    docx_files = list(base_dir.glob("*.docx"))
    if not docx_files:
        print("目录下未找到 docx 文件")
        return

    for docx_path in docx_files:
        md_path = docx_path.with_suffix(".md")

        def image_converter(image):
            """
            图片处理函数：保存图片并返回 Markdown 引用
            """
            image_name = f"{docx_path.stem}_{image.alt_text or image.content_type.replace('/', '_')}.png"
            image_file = image_dir / image_name

            with image.open() as image_bytes:
                with open(image_file, "wb") as f:
                    f.write(image_bytes.read())

            return {
                "src": f"images/{image_name}"
            }

        with open(docx_path, "rb") as docx_file:
            result = mammoth.convert_to_markdown(
                docx_file,
                convert_image=mammoth.images.img_element(image_converter)
            )

        md_content = result.value

        # 可选：简单后处理（增强 Markdown 规范性）
        md_content = postprocess_markdown(md_content)

        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        print(f"转换完成: {docx_path.name} -> {md_path.name}")


def postprocess_markdown(md: str) -> str:
    """
    可扩展的 Markdown 后处理：
    - 清理多余空行
    - 统一标题格式
    """
    lines = md.splitlines()
    cleaned = []
    for line in lines:
        cleaned.append(line.rstrip())
    return "\n".join(cleaned)

if __name__ == "__main__":
    # 这里填你要测试的拆分后 Word 目录
    type = "环境评估报告"
    folder_name = "test3"

    try:
        convert_docx_dir_to_md(type, folder_name)
    except Exception as e:
        print(f"[ERROR] 转换失败: {e}")
