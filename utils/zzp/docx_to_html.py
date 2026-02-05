import mammoth
import os
import logging
import uuid
import sys
import shutil
from urllib.parse import unquote
from bs4 import BeautifulSoup

# 添加项目根目录到 sys.path 以便导入 server_config
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if project_root not in sys.path:
    sys.path.append(project_root)

try:
    import server_config
except ImportError:
    # 尝试相对导入或假设在 path 中
    try:
        from ... import server_config
    except ImportError:
        logging.warning("server_config import failed in docx_to_html")

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _get_image_converter(user_id=None, image_output_dir=None, image_url_prefix=None):
    """
    工厂函数：返回一个用于 mammoth 的 convert_image 处理函数
    """
    def convert_image(image):
        try:
            # 确保目录存在
            if image_output_dir and image_url_prefix:
                save_dir = image_output_dir
                url_prefix = image_url_prefix
            elif user_id:
                save_dir = server_config.get_user_editor_image_dir(user_id)
                # 修改 URL 前缀以匹配前端代理规则 (/python-api -> 后端)
                url_prefix = f"/python-api/editor_images/{user_id}/"
            else:
                save_dir = server_config.EDITOR_IMAGE_DIR
                url_prefix = "/python-api/editor_images/"
            
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)

            # 生成唯一文件名
            ext = image.content_type.split("/")[-1]
            if not ext: ext = "png"
            filename = f"{uuid.uuid4()}.{ext}"
            file_path = os.path.join(save_dir, filename)

            # 保存图片
            with image.open() as image_bytes:
                with open(file_path, "wb") as f:
                    f.write(image_bytes.read())

            return {
                "src": f"{url_prefix}{filename}"
            }
        except Exception as e:
            logger.error(f"图片提取失败: {e}")
            return {"src": ""}
            
    return mammoth.images.img_element(convert_image)

def convert_docx_to_html(docx_path, user_id=None, image_output_dir=None, image_url_prefix=None):
    """
    将 docx 文件转换为 HTML 文件。
    生成的 HTML 文件将与 docx 文件同名，但在同一目录下，后缀为 .html。
    图片将被提取并保存到 editor_images 目录，HTML 中使用 URL 引用。
    
    参数扩展：
    - image_output_dir: 图片物理保存目录 (例如: /root/.../report_name/images)
    - image_url_prefix: 图片 URL 前缀 (例如: /python-api/report_files/.../images/)
    """
    if not os.path.exists(docx_path):
        logger.error(f"文件不存在: {docx_path}")
        return False

    html_path = os.path.splitext(docx_path)[0] + ".html"
    
    try:
        with open(docx_path, "rb") as docx_file:
            # 使用 mammoth 转换为 HTML
            # 使用自定义 convert_image 处理图片
            result = mammoth.convert_to_html(
                docx_file, 
                ignore_empty_paragraphs=True,
                convert_image=_get_image_converter(user_id, image_output_dir, image_url_prefix)
            )
            html_content = result.value
            messages = result.messages
            
            # 打印警告信息（忽略常见的样式缺失警告，避免刷屏）
            for message in messages:
                # 过滤掉 "Unrecognised paragraph style" 类型的警告，通常不影响阅读
                if message.type == "warning" and "Unrecognised paragraph style" in message.message:
                    continue
                # 过滤掉 "Paragraph style with ID ... was referenced but not defined"
                if message.type == "warning" and "referenced but not defined" in message.message:
                    continue
                    
                logger.warning(f"Mammoth 转换警告: {message}")

        # 写入 HTML 文件
        # 为了更好地支持中文，指定 utf-8 编码
        with open(html_path, "w", encoding="utf-8") as html_file:
            html_file.write(html_content)
            
        logger.debug(f"HTML 生成成功: {html_path}")
        return True

    except Exception as e:
        logger.error(f"转换 HTML 失败: {docx_path}, 错误: {e}", exc_info=True)
        return False

def convert_docx_list_to_merged_html(docx_paths, output_html_path, user_id=None, image_output_dir=None, image_url_prefix=None):
    try:
        html_parts = []
        for docx_path in docx_paths:
            html_path = os.path.splitext(docx_path)[0] + ".html"
            content = ""
            if os.path.exists(html_path):
                try:
                    with open(html_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    
                    # [FIX] 复用现有 HTML 时，迁移图片到 report_merge 目录并更新链接
                    if content and image_output_dir and image_url_prefix:
                        try:
                            soup = BeautifulSoup(content, 'html.parser')
                            has_changes = False
                            for img in soup.find_all('img'):
                                src = img.get('src')
                                if not src: continue
                                
                                # 仅处理本地编辑器图片
                                if "editor_images/" in src:
                                    try:
                                        # 1. 解析相对路径
                                        if "/python-api/editor_images/" in src:
                                            relative_path = src.split("/python-api/editor_images/", 1)[1]
                                        elif "/editor_images/" in src:
                                            relative_path = src.split("/editor_images/", 1)[1]
                                        else:
                                            continue
                                        
                                        relative_path = unquote(relative_path).lstrip("/")
                                        
                                        # 2. 定位源文件
                                        # 尝试获取 EDITOR_IMAGE_DIR
                                        source_root = getattr(server_config, 'EDITOR_IMAGE_DIR', None)
                                        if not source_root:
                                            source_root = os.path.join(project_root, "editor_image")
                                            
                                        source_full_path = os.path.join(source_root, relative_path)
                                        
                                        # 3. 复制文件并更新路径
                                        if os.path.exists(source_full_path):
                                            filename = os.path.basename(relative_path)
                                            if not os.path.exists(image_output_dir):
                                                os.makedirs(image_output_dir)
                                            
                                            target_full_path = os.path.join(image_output_dir, filename)
                                            
                                            # 避免自我复制
                                            if os.path.abspath(source_full_path) != os.path.abspath(target_full_path):
                                                shutil.copy2(source_full_path, target_full_path)
                                            
                                            # 更新 src 为新的 merged 路径
                                            new_src = f"{image_url_prefix}{filename}"
                                            img['src'] = new_src
                                            has_changes = True
                                        else:
                                            logger.warning(f"合并处理：源图片不存在 {source_full_path}")
                                    except Exception as img_e:
                                        logger.warning(f"合并处理：图片迁移失败 {src}: {img_e}")
                            
                            if has_changes:
                                content = str(soup)
                                
                        except Exception as soup_e:
                            logger.error(f"合并处理：HTML解析失败 {html_path}: {soup_e}")
                            
                except Exception as e:
                    content = ""
            if not content:
                try:
                    with open(docx_path, "rb") as docx_file:
                        result = mammoth.convert_to_html(
                            docx_file, 
                            ignore_empty_paragraphs=True,
                            convert_image=_get_image_converter(user_id, image_output_dir, image_url_prefix)
                        )
                        content = result.value
                except Exception as e:
                    content = ""
            if content:
                html_parts.append(content)
        final_html = "".join(html_parts)
        with open(output_html_path, "w", encoding="utf-8") as f:
            f.write(final_html)
        return True
    except Exception as e:
        logger.error(f"合并 HTML 失败: {output_html_path}, 错误: {e}", exc_info=True)
        return False
