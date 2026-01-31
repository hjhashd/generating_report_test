import os
import logging
from docx import Document
from htmldocx import HtmlToDocx

# 添加父目录到 sys.path 以导入 server_config
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import server_config

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def convert_html_to_docx(html_content, output_docx_path):
    """
    将 HTML 字符串内容转换为 Word 文档并保存。
    如果 output_docx_path 已存在，将会被覆盖。
    """
    try:
        # 预处理 HTML 内容：替换图片路径
        # 将 web 路径 /python-api/editor_images/ 替换为本地绝对路径
        # 这样 htmldocx 才能找到并嵌入图片
        web_img_prefix = "/python-api/editor_images/"
        local_img_dir = os.path.join(server_config.EDITOR_IMAGE_DIR, "")
        
        if web_img_prefix in html_content:
            html_content = html_content.replace(web_img_prefix, local_img_dir)
            logger.info(f"已修正图片路径: {web_img_prefix} -> {local_img_dir}")

        # 创建一个新的 Document 对象
        doc = Document()
        
        # 初始化转换器
        new_parser = HtmlToDocx()
        
        # 将 HTML 转换为 Docx 内容
        # 注意：htmldocx 默认会把内容追加到 doc 中
        new_parser.add_html_to_document(html_content, doc)
        
        # --- 图片自动调整大小 ---
        # 遍历文档中的所有内嵌图片，如果宽度超过页面可用宽度，则等比例缩小
        try:
            for section in doc.sections:
                # 计算可用宽度：页面宽度 - 左边距 - 右边距
                available_width = section.page_width - section.left_margin - section.right_margin
                
                # 遍历文档中的所有内嵌形状（主要是图片）
                for shape in doc.inline_shapes:
                    if shape.width > available_width:
                        # 计算宽高比
                        aspect_ratio = shape.height / shape.width
                        
                        # 调整为可用宽度
                        shape.width = available_width
                        shape.height = int(available_width * aspect_ratio)
                        
                        logger.info(f"图片尺寸已调整: 宽度限制为 {available_width} EMU")
        except Exception as img_err:
            logger.warning(f"图片尺寸调整过程中出现警告 (不影响文档生成): {img_err}")
        # -----------------------
        
        # 保存文件
        doc.save(output_docx_path)
        logger.info(f"✅ HTML -> Word 转换成功: {output_docx_path}")
        return True
        
    except Exception as e:
        logger.error(f"❌ HTML -> Word 转换失败: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    # 测试代码
    test_html = "<h1>测试标题</h1><p>这是一个<b>测试</b>段落。</p>"
    test_path = "test_output.docx"
    convert_html_to_docx(test_html, test_path)
