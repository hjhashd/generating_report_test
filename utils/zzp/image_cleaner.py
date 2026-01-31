import os
import logging
import re
import glob
from typing import Set, List

# 添加父目录到 sys.path 以导入 server_config
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import server_config

logger = logging.getLogger(__name__)

def get_all_user_images(user_id: str) -> Set[str]:
    """获取用户目录下所有上传的图片文件名"""
    img_root = server_config.EDITOR_IMAGE_DIR
    dirs = [
        server_config.get_user_editor_image_dir(user_id),
        os.path.join(img_root, "report", str(user_id)),
        os.path.join(img_root, "report_merge", str(user_id))
    ]
    results = set()
    for base_dir in dirs:
        if not os.path.exists(base_dir):
            continue
        for root, _, files in os.walk(base_dir):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, img_root).replace(os.sep, "/")
                results.add(rel_path)
    return results

def get_referenced_images(user_id: str) -> Set[str]:
    """
    扫描用户所有的 HTML 报告，提取引用的图片文件名。
    """
    referenced_files = set()
    
    # 需要扫描的根目录列表
    scan_roots = [
        server_config.get_user_report_dir(user_id),
        server_config.get_user_merge_dir(user_id)
    ]
    
    # 正则匹配 src="/python-api/editor_images/{user_id}/xxx.png"
    # 注意：前端可能使用相对路径或绝对路径，这里匹配文件名核心部分
    # 假设 URL 模式是 .../editor_images/user_id/filename
    # 或者直接匹配文件名（比较宽松，防止漏删）
    # 但为了严谨，我们匹配包含 user_id 的路径特征
    
    # 构造正则: 匹配 /python-api/editor_images/user_id/([\w\-\.]+)\b
    # 或者 simple check: just look for the filename in the content? 
    # No, filename might be "image.png" which is too common.
    # Our filenames are timestamp_uuid.ext, so they are quite unique.
    # Let's use strict regex.
    
    # URL Prefix logic from editor_api.py: f"{user_id}/{new_filename}"
    # Front end likely prepends /python-api/editor_images/
    
    pattern = re.compile(r"/editor_images/([^\"\'\s\)]+)")
    
    for root_dir in scan_roots:
        if not os.path.exists(root_dir):
            continue
            
        # 递归查找所有 .html 文件
        for root, dirs, files in os.walk(root_dir):
            for file in files:
                if file.endswith(".html"):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            content = f.read()
                            # 查找匹配
                            matches = pattern.findall(content)
                            for match in matches:
                                referenced_files.add(match)
                    except Exception as e:
                        logger.warning(f"读取文件失败 {file_path}: {e}")
                        
    return referenced_files

def clean_orphaned_images(user_id: str, dry_run: bool = False) -> dict:
    """
    清理孤儿图片
    :param user_id: 用户ID
    :param dry_run: 如果为 True，只返回待删除列表，不执行删除
    :return: 结果字典
    """
    try:
        # 1. 获取物理存在的所有图片
        existing_images = get_all_user_images(user_id)
        if not existing_images:
            return {"deleted_count": 0, "details": [], "message": "没有图片需要清理"}
            
        # 2. 获取被引用的图片
        referenced_images = get_referenced_images(user_id)
        
        # 3. 计算差集 (存在 - 引用 = 孤儿)
        orphaned_images = existing_images - referenced_images
        
        deleted_files = []
        img_root = server_config.EDITOR_IMAGE_DIR

        for img_name in orphaned_images:
            normalized = os.path.normpath(img_name.replace("/", os.sep))
            if os.path.isabs(normalized) or normalized.startswith(".."):
                continue
            file_path = os.path.join(img_root, normalized)
            if not dry_run:
                try:
                    os.remove(file_path)
                    deleted_files.append(img_name)
                    logger.info(f"已清理孤儿图片: {file_path}")
                except Exception as e:
                    logger.error(f"删除失败 {file_path}: {e}")
            else:
                deleted_files.append(img_name)
                
        return {
            "deleted_count": len(deleted_files),
            "details": deleted_files,
            "dry_run": dry_run,
            "message": "清理完成"
        }
        
    except Exception as e:
        logger.error(f"清理过程异常: {e}", exc_info=True)
        return {"error": str(e)}

if __name__ == "__main__":
    # Test
    # print(clean_orphaned_images("test_user_id", dry_run=True))
    pass
