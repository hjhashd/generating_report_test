from docx import Document


def analyze_document_structure(file_path):
    """分析文档结构，提取所有标题信息"""
    doc = Document(file_path)

    result = {
        'title': '',  # 文档标题（如果有）
        'headings': [],
        'heading_count': {}
    }

    # 尝试获取文档核心属性中的标题
    if doc.core_properties.title:
        result['title'] = doc.core_properties.title

    # 遍历所有段落
    for idx, paragraph in enumerate(doc.paragraphs):
        style = paragraph.style.name

        # 检查是否为标题样式
        if style.startswith('Heading'):
            level = style.replace('Heading ', '')

            heading_info = {
                'index': idx,
                'level': int(level) if level.isdigit() else level,
                'text': paragraph.text.strip(),
                'style': style
            }

            result['headings'].append(heading_info)

            # 统计各级标题数量
            result['heading_count'][level] = result['heading_count'].get(level, 0) + 1

    return result


# 使用示例
if __name__ == "__main__":
    file_path = "generate_report/utils/zzp/word拆分/附录X-1：信息系统建设与升级改造类（开发实施类）信息化项目可行性研究报告模板V6.0.docx"

    structure = analyze_document_structure(file_path)

    print(f"文档标题: {structure['title']}")
    print(f"\n找到 {len(structure['headings'])} 个标题:")
    print("-" * 50)

    for heading in structure['headings']:
        indent = "  " * (heading['level'] - 1)
        print(f"{indent}{'•' * heading['level']} {heading['text']}")

    print("\n标题统计:")
    for level, count in sorted(structure['heading_count'].items()):
        print(f"  级别{level}: {count}个")