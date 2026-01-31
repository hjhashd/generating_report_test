#!/usr/bin/env python3
"""
Word文档内容提取工具 - 支持表格、图片、格式化文本等
根据标题提取内容并保存为新文档
"""

import os
import sys
import zipfile
import shutil
from pathlib import Path
import xml.etree.ElementTree as ET

# Word命名空间
NAMESPACES = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
    'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'
}

# 注册命名空间
for prefix, uri in NAMESPACES.items():
    ET.register_namespace(prefix, uri)


class DocxExtractor:
    """Word文档提取器"""

    def __init__(self, docx_path):
        self.docx_path = docx_path
        self.temp_dir = None
        self.document_xml = None
        self.tree = None
        self.root = None

    def __enter__(self):
        """上下文管理器入口"""
        self.unpack()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出，清理临时文件"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def unpack(self):
        """解压docx文件"""
        self.temp_dir = f"{self.docx_path}_temp"

        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

        with zipfile.ZipFile(self.docx_path, 'r') as zip_ref:
            zip_ref.extractall(self.temp_dir)

        # 读取主文档XML
        self.document_xml = os.path.join(self.temp_dir, 'word', 'document.xml')
        self.tree = ET.parse(self.document_xml)
        self.root = self.tree.getroot()

        print(f"✓ 已解压文档到: {self.temp_dir}")

    def get_paragraph_text(self, para_elem):
        """获取段落的纯文本内容"""
        texts = []
        for t_elem in para_elem.findall('.//w:t', NAMESPACES):
            if t_elem.text:
                texts.append(t_elem.text)
        return ''.join(texts)

    def is_heading(self, para_elem):
        """判断段落是否为标题，返回(是否为标题, 样式名称, 级别)"""
        style_elem = para_elem.find('.//w:pStyle', NAMESPACES)
        if style_elem is not None:
            style_val = style_elem.get(f'{{{NAMESPACES["w"]}}}val', '')

            # 支持英文样式 Heading1, Heading2...
            if style_val.startswith('Heading'):
                level = style_val.replace('Heading', '').strip()
                try:
                    level_num = int(level) if level else 1
                except:
                    level_num = 1
                return True, style_val, level_num

            # 支持中文样式 标题1, 标题2...
            if style_val.startswith('标题'):
                level = style_val.replace('标题', '').strip()
                try:
                    level_num = int(level) if level else 1
                except:
                    level_num = 1
                return True, style_val, level_num

        return False, None, None

    def find_heading_indices(self, target_heading):
        """
        查找目标标题在body中的索引位置
        返回: (起始索引, 结束索引) 或 None

        逻辑：找到目标标题后，继续到遇见同级或更高级的标题为止
        """
        body = self.root.find('.//w:body', NAMESPACES)
        if body is None:
            return None

        start_idx = None
        end_idx = None
        target_level = None

        for idx, child in enumerate(body):
            # 只处理段落元素
            if child.tag == f'{{{NAMESPACES["w"]}}}p':
                is_head, style, level = self.is_heading(child)
                if is_head:
                    text = self.get_paragraph_text(child).strip()

                    if text == target_heading:
                        start_idx = idx
                        target_level = level
                        print(f"✓ 找到目标标题 '{target_heading}' 在索引 {idx}，级别 {level}")
                    elif start_idx is not None and end_idx is None:
                        # 遇到同级或更高级标题时结束
                        if level <= target_level:
                            end_idx = idx
                            print(f"✓ 找到同级/更高级标题 '{text}'（级别{level}），结束索引 {idx}")
                            break

        # 如果找到起始但没有结束，说明到文档末尾
        if start_idx is not None and end_idx is None:
            end_idx = len(list(body))
            print(f"✓ 内容延伸到文档末尾，结束索引 {end_idx}")

        return (start_idx, end_idx) if start_idx is not None else None

    def extract_to_new_document(self, target_heading, output_path):
        """
        提取指定标题的内容到新文档
        完整复制所有元素：段落、表格、图片等
        """
        # 查找标题位置
        indices = self.find_heading_indices(target_heading)
        if indices is None:
            print(f"❌ 未找到标题: {target_heading}")
            return False

        start_idx, end_idx = indices

        # 创建新文档目录
        output_temp = f"{output_path}_temp"
        if os.path.exists(output_temp):
            shutil.rmtree(output_temp)

        # 复制整个文档结构
        shutil.copytree(self.temp_dir, output_temp)

        # 读取新文档的document.xml
        new_doc_xml = os.path.join(output_temp, 'word', 'document.xml')
        new_tree = ET.parse(new_doc_xml)
        new_root = new_tree.getroot()
        new_body = new_root.find('.//w:body', NAMESPACES)

        # 清空新body的内容
        for child in list(new_body):
            new_body.remove(child)

        # 复制指定范围的所有元素（注意：要深拷贝，不要直接append原始元素）
        body = self.root.find('.//w:body', NAMESPACES)
        extracted_count = 0

        import copy
        for idx, child in enumerate(list(body)):
            if start_idx <= idx < end_idx:
                # 深拷贝元素，避免影响原始文档
                new_child = copy.deepcopy(child)
                new_body.append(new_child)
                extracted_count += 1

        # 保存修改后的document.xml
        new_tree.write(new_doc_xml, encoding='UTF-8', xml_declaration=True)

        print(f"✓ 已提取 {extracted_count} 个元素（段落/表格/图片等）")

        # 打包成新的docx文件
        self.pack(output_temp, output_path)

        # 清理临时目录
        shutil.rmtree(output_temp)

        print(f"✓ 成功保存到: {output_path}")
        return True

    def pack(self, directory, output_path):
        """将目录打包为docx文件"""
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(directory):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, directory)
                    zipf.write(file_path, arcname)

    def list_all_headings(self):
        """列出文档中的所有标题"""
        body = self.root.find('.//w:body', NAMESPACES)
        if body is None:
            return []

        headings = []
        for idx, child in enumerate(body):
            if child.tag == f'{{{NAMESPACES["w"]}}}p':
                is_head, style, level = self.is_heading(child)
                if is_head:
                    text = self.get_paragraph_text(child).strip()
                    headings.append({
                        'index': idx,
                        'level': level,
                        'style': style,
                        'text': text
                    })

        return headings


def list_headings(docx_path):
    """列出文档的所有标题"""
    print(f"\n{'=' * 60}")
    print(f"📄 文档标题列表: {docx_path}")
    print(f"{'=' * 60}")

    with DocxExtractor(docx_path) as extractor:
        headings = extractor.list_all_headings()

        if not headings:
            print("未找到任何标题")
            return []

        for h in headings:
            level = h['level']
            indent = "  " * (level - 1) if isinstance(level, int) else ""
            print(f"{indent}[级别{level}] {h['text']}")

        print(f"{'=' * 60}")
        print(f"共找到 {len(headings)} 个标题\n")

        return headings


def extract_content(docx_path, target_heading, output_path=None):
    """
    提取指定标题的内容

    参数:
        docx_path: 输入的Word文档路径
        target_heading: 目标标题文本
        output_path: 输出文档路径（可选）
    """
    if output_path is None:
        base_name = os.path.splitext(os.path.basename(docx_path))[0]
        safe_heading = target_heading.replace('/', '_').replace('\\', '_')[:50]
        output_path = f"{base_name}_{safe_heading}.docx"

    print(f"\n{'=' * 60}")
    print(f"开始提取内容")
    print(f"{'=' * 60}")
    print(f"输入文档: {docx_path}")
    print(f"目标标题: {target_heading}")
    print(f"输出文档: {output_path}")
    print(f"{'=' * 60}\n")

    with DocxExtractor(docx_path) as extractor:
        success = extractor.extract_to_new_document(target_heading, output_path)

    if success:
        print(f"\n✅ 提取完成！")
        print(f"📁 输出文件: {output_path}")
    else:
        print(f"\n❌ 提取失败")

    return success


def batch_extract(docx_path, heading_list, output_dir=None):
    """批量提取多个标题"""
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'=' * 60}")
    print(f"批量提取模式 - 共 {len(heading_list)} 个标题")
    print(f"{'=' * 60}\n")

    results = []

    for i, heading in enumerate(heading_list, 1):
        print(f"\n[{i}/{len(heading_list)}] 处理标题: {heading}")
        print(f"{'-' * 60}")

        base_name = os.path.splitext(os.path.basename(docx_path))[0]
        safe_heading = heading.replace('/', '_').replace('\\', '_')[:50]

        if output_dir:
            output_path = os.path.join(output_dir, f"{base_name}_{safe_heading}.docx")
        else:
            output_path = f"{base_name}_{safe_heading}.docx"

        with DocxExtractor(docx_path) as extractor:
            success = extractor.extract_to_new_document(heading, output_path)

        results.append({
            'heading': heading,
            'output': output_path if success else None,
            'success': success
        })

    # 打印汇总
    print(f"\n{'=' * 60}")
    print(f"📊 批量提取完成")
    print(f"{'=' * 60}")

    success_count = sum(1 for r in results if r['success'])
    print(f"成功: {success_count}/{len(results)}")

    for r in results:
        status = "✓" if r['success'] else "✗"
        print(f"  {status} {r['heading']}")

    return results


def main():
    """主函数 - 命令行界面"""

    if len(sys.argv) < 2:
        print("用法示例:")
        print("  1. 列出所有标题:")
        print("     python script.py list 文档.docx")
        print("")
        print("  2. 提取单个标题:")
        print("     python script.py extract 文档.docx '第一章'")
        print("     python script.py extract 文档.docx '第一章' 输出.docx")
        print("")
        print("  3. 批量提取:")
        print("     python script.py batch 文档.docx '第一章' '第二章' '第三章'")
        print("     python script.py batch 文档.docx --output=输出目录 '第一章' '第二章'")
        return

    command = sys.argv[1]

    if command == 'list':
        if len(sys.argv) < 3:
            print("❌ 请指定文档路径")
            return

        docx_path = sys.argv[2]
        if not os.path.exists(docx_path):
            print(f"❌ 文件不存在: {docx_path}")
            return

        list_headings(docx_path)

    elif command == 'extract':
        if len(sys.argv) < 4:
            print("❌ 请指定文档路径和标题")
            return

        docx_path = sys.argv[2]
        target_heading = sys.argv[3]
        output_path = sys.argv[4] if len(sys.argv) > 4 else None

        if not os.path.exists(docx_path):
            print(f"❌ 文件不存在: {docx_path}")
            return

        extract_content(docx_path, target_heading, output_path)

    elif command == 'batch':
        if len(sys.argv) < 4:
            print("❌ 请指定文档路径和至少一个标题")
            return

        docx_path = sys.argv[2]

        # 检查是否指定输出目录
        output_dir = None
        start_idx = 3
        if sys.argv[3].startswith('--output='):
            output_dir = sys.argv[3].split('=')[1]
            start_idx = 4

        heading_list = sys.argv[start_idx:]

        if not os.path.exists(docx_path):
            print(f"❌ 文件不存在: {docx_path}")
            return

        batch_extract(docx_path, heading_list, output_dir)

    else:
        print(f"❌ 未知命令: {command}")
        print("可用命令: list, extract, batch")


if __name__ == "__main__":
    # 如果直接运行，可以在这里设置测试参数

    # 示例1: 列出标题
    # list_headings("示例文档.docx")

    # 示例2: 提取单个标题
    # extract_content("示例文档.docx", "第一章")

    # 示例3: 批量提取
    # batch_extract("示例文档.docx", ["第一章", "第二章", "第三章"], output_dir="extracted")

    # 命令行模式
    # main()
    target = ["深圳数据交易所-数据商纪念证书","贵州省数据流通交易服务中心-数据商凭证","中国电子信息行业联合会会员"]
    batch_extract("XA_证书.docx",target,)