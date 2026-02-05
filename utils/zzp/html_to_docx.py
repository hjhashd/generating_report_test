import os
import logging
import re
from docx import Document
from htmldocx import HtmlToDocx
from bs4 import BeautifulSoup
from urllib.parse import unquote
from docx.enum.style import WD_STYLE_TYPE
from docx.shared import Pt

# 添加父目录到 sys.path 以导入 server_config
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import server_config

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def ensure_heading_style(doc, level):
    """确保文档中存在指定的标题样式，不存在则创建"""
    style_name = f'Heading {level}'
    try:
        return doc.styles[style_name]
    except KeyError:
        try:
            style = doc.styles.add_style(style_name, WD_STYLE_TYPE.PARAGRAPH)
            # 尝试设置基本样式
            style.base_style = doc.styles['Normal']
            font = style.font
            font.name = 'Arial'  # 或其它通用字体
            font.bold = True
            # 简单的字号设置
            sizes = {1: 16, 2: 14, 3: 13, 4: 12} 
            font.size = Pt(sizes.get(level, 12))
            logger.info(f"已自动创建缺失样式: {style_name}")
            return style
        except Exception as e:
            logger.warning(f"无法创建样式 {style_name}: {e}")
            return None

def auto_repair_headings(doc):
    """
    自动修复文档中的标题样式
    检测类似 "1 标题", "1.1 标题", "一、标题" 的段落，
    如果它们是 Normal 样式，则将其升级为 Heading 样式。
    """
    for para in doc.paragraphs:
        # 如果已经是标题样式，跳过
        if para.style.name.startswith('Heading'):
            continue
            
        text = para.text.strip()
        if not text:
            continue
            
        # 限制长度，防止误判长文本
        # 标题通常很短，超过 50 个字符极大概率是正文
        if len(text) > 50:
            continue
            
        # 排除以标点符号结尾的段落 (标题通常不以句号、分号、冒号结尾)
        if text[-1] in ['。', '；', '：', ':', ';', '.', ',']:
            continue

        # 匹配 "1 标题", "1.1 标题", "1. 标题", "1.1. 标题", "1、标题"
        # 改进正则：支持顿号，支持无空格但有标点的情况
        match = re.match(r'^(\d+(\.\d+)*)[.、]?\s*', text)
        if match:
            # 必须确保不仅仅是数字，比如 "2023年" 不应该被匹配
            # 简单的逻辑：如果匹配到的只是数字，且后面没有分隔符也没有空格，可能会误判
            # 这里我们假设标题通常很短，且符合结构。
            # 为了避免 "2023 text" 被误判为 "2023" 级标题（不存在），我们需要检查层级
            
            num_str = match.group(1)
            level = num_str.count('.') + 1
            if level > 9: level = 9
            
            # 只有当看起来像标题时才应用 (例如包含 . 或者是纯数字但后面有空格)
            # 之前的正则 r'^(\d+(\.\d+)*)\.?\s+' 强制要求有空格。
            # 现在的正则允许无空格，但必须有分隔符吗？
            # 让我们稍微保守一点：必须有 . 或 、 或 空格
            
            # 重新匹配以确认分隔符
            if re.match(r'^(\d+(\.\d+)*)([.、]|\s)', text):
                 # 特殊处理：如果使用的是顿号 "、" 且后面紧跟文字，需要更严格的判断
                 # 因为 "1、本文件..." 这种列表项太常见了
                 if '、' in text[:10]:
                     # 如果是 "1、" 开头，且长度超过 20，或者包含逗号，大概率是列表
                     if len(text) > 20 or '，' in text or ',' in text:
                         continue
                 
                 # 确保样式存在
                 ensure_heading_style(doc, level)
                 try:
                    para.style = f'Heading {level}'
                 except KeyError:
                    pass
                 continue
            
        # 匹配 "一、标题", "第一章 标题"
        if re.match(r'^[一二三四五六七八九十]+、', text) or re.match(r'^第[一二三四五六七八九十]+[章节]', text):
            ensure_heading_style(doc, 1)
            try:
                para.style = 'Heading 1'
            except KeyError:
                pass
            continue

def convert_html_to_docx(html_content, output_docx_path):
    """
    将 HTML 字符串内容转换为 Word 文档并保存。
    如果 output_docx_path 已存在，将会被覆盖。
    """
    try:
        # 预处理 HTML 内容：替换图片路径
        # [FIX] 使用 BeautifulSoup 解析并处理 URL 编码问题
        # 将 web 路径 /python-api/editor_images/ 替换为本地绝对路径
        if "/editor_images/" in html_content:
            try:
                soup = BeautifulSoup(html_content, 'html.parser')
                has_changes = False
                
                # 获取本地图片根目录
                # 优先尝试从 server_config 获取，如果未定义则回退
                local_img_root = getattr(server_config, 'EDITOR_IMAGE_DIR', None)
                if not local_img_root:
                    local_img_root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "editor_image")
                
                for img in soup.find_all('img'):
                    src = img.get('src')
                    if not src: continue
                    
                    # 识别是否为编辑器图片路径
                    relative_path = None
                    if "/python-api/editor_images/" in src:
                        relative_path = src.split("/python-api/editor_images/", 1)[1]
                    elif "/editor_images/" in src:
                        relative_path = src.split("/editor_images/", 1)[1]
                    
                    if relative_path:
                        # [CRITICAL] URL 解码，处理中文路径
                        decoded_path = unquote(relative_path).lstrip("/")
                        
                        # 拼接本地完整路径
                        full_path = os.path.join(local_img_root, decoded_path)
                        
                        # 只有当文件确实存在时才替换，避免把无效链接替换成更无效的本地路径
                        # (虽然 htmldocx 对于本地不存在的路径也无能为力，但至少逻辑正确)
                        if os.path.exists(full_path):
                            img['src'] = full_path
                            has_changes = True
                            logger.debug(f"修正图片路径: {src} -> {full_path}")
                        else:
                            logger.warning(f"图片文件未找到: {full_path} (原始 src: {src})")
                
                if has_changes:
                    html_content = str(soup)
                    logger.info("已批量完成图片路径修正 (含 URL 解码)")
                    
            except Exception as soup_e:
                logger.error(f"解析 HTML 图片路径失败: {soup_e}")
                # Fallback: 如果解析失败，尝试回退到简单的字符串替换 (虽然不支持中文，但总比没有好)
                web_img_prefix = "/python-api/editor_images/"
                local_img_dir = os.path.join(server_config.EDITOR_IMAGE_DIR, "")
                if web_img_prefix in html_content:
                    html_content = html_content.replace(web_img_prefix, local_img_dir)

        # 创建一个新的 Document 对象
        doc = Document()
        
        # 初始化转换器
        new_parser = HtmlToDocx()
        
        # 将 HTML 转换为 Docx 内容
        # 注意：htmldocx 默认会把内容追加到 doc 中
        new_parser.add_html_to_document(html_content, doc)
        
        # [NEW] 自动修复标题样式
        # 针对 Tiptap 等编辑器可能输出 <p>1. 标题</p> 而非 <h1>1. 标题</h1> 的情况
        auto_repair_headings(doc)

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
