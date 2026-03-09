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
            
    # 获取项目根目录的绝对路径 (当前文件在 utils/ 目录下)
    # /app/utils/log_config.py -> /app
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 配置基础日志
    handlers = [
        logging.StreamHandler(sys.stdout)
    ]
    
    # 如果是开发环境，额外写入 logs/test_report.log
    if env == "development":
        log_dir = os.path.join(project_root, "logs")
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        # 使用绝对路径，确保在任何地方启动都能正确写入
        log_file = os.path.join(log_dir, "test_report.log")
        handlers.append(logging.FileHandler(log_file))
    elif env == "production":
        # 生产环境使用绝对路径写入 report.log
        log_file = os.path.join(project_root, "report.log")
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=handlers
    )
    
    # 降低特定模块的日志级别，减少噪音
    noisy_loggers = [
        "utils.lyf.prompt_chat_async",  # list_sessions, SQL 等频繁日志
    ]
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)
    
    # 针对 uvicorn 的日志进行劫持，确保它们也流向 root logger 的 handlers
    for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        u_logger = logging.getLogger(logger_name)
        # 清除 uvicorn 自带的 handlers，让它通过 propagate 流向 root logger
        for handler in u_logger.handlers[:]:
            u_logger.removeHandler(handler)
        u_logger.propagate = True

    logger = logging.getLogger("log_config")
    logger.info(f"✅ 日志系统初始化完成 | 环境: {env}")
