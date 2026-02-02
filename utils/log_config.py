import logging
import os
import sys

def setup_logging():
    """
    统一日志配置中心
    旨在替代散落在各处的 logging.basicConfig
    """
    # 获取环境变量
    env = os.getenv("ENV", "development")
    
    # 定义日志格式
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # 强制重新配置 (force=True 在 Python 3.8+ 可用)
    # 如果是低版本，需要先移除 handlers
    root_logger = logging.getLogger()
    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            
    # 配置基础日志
    # 默认输出到 stdout/stderr，由外部 Shell 或 Docker 接管文件写入
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        stream=sys.stdout
    )
    
    # 可以在这里添加针对特定模块的日志级别调整
    # logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    logger = logging.getLogger("log_config")
    logger.info(f"✅ 日志系统初始化完成 | 环境: {env}")
