import os

# 动态加载父级 utils 目录下的 sql_config.py
# 逻辑：当前文件在 utils/zzp/sql_config.py -> 父目录 utils -> 目标文件 utils/sql_config.py
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_utils_dir = os.path.dirname(current_dir)
config_path = os.path.join(parent_utils_dir, 'sql_config.py')

# 执行父配置文件的内容，将其注入当前命名空间
# 这样当前模块就会拥有父配置文件中定义的所有变量 (username, password, host 等)
with open(config_path, 'r', encoding='utf-8') as f:
    exec(f.read())
