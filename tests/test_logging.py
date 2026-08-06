"""ADR-0012 Issue 5：结构化日志测试

验证标准 logging 模块的集成——日志级别、时间戳、模块名、文件落盘。
"""
import logging
import tempfile
from pathlib import Path

import pytest

from core.logging_utils import (
    get_logger,
    log,  # 兼容旧接口
    set_log_func,  # UI 桥接
    setup_logging,
)


class TestStructuredLogging:
    """验证结构化日志功能。"""

    @pytest.fixture
    def log_dir(self):
        tmp = tempfile.mkdtemp()
        yield Path(tmp)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    def test_setup_creates_logger(self, log_dir):
        """setup_logging 应创建可用的 logger。"""
        setup_logging(log_dir=log_dir, level=logging.DEBUG, reset=True)
        logger = get_logger("test")
        assert logger is not None
        assert logger.getEffectiveLevel() == logging.DEBUG

    def test_log_levels(self, log_dir):
        """各日志级别应正常工作。"""
        setup_logging(log_dir=log_dir, level=logging.DEBUG, reset=True)
        logger = get_logger("test_levels")

        # 不应抛异常
        logger.debug("debug msg")
        logger.info("info msg")
        logger.warning("warning msg")
        logger.error("error msg")

    def test_log_writes_to_file(self, log_dir):
        """日志应同时输出到文件。"""
        setup_logging(log_dir=log_dir, level=logging.INFO, reset=True)
        logger = get_logger("test_file")

        logger.info("测试日志消息")
        logger.warning("测试警告")

        # 强制刷新所有 handler
        for handler in logging.getLogger().handlers:
            handler.flush()
            if hasattr(handler, 'close'):
                handler.close()

        # 查找日志文件
        log_files = list(log_dir.glob("*.log*"))
        assert len(log_files) > 0, f"未找到日志文件，目录内容: {list(log_dir.iterdir())}"

        content = log_files[0].read_text(encoding='utf-8')
        assert "测试日志消息" in content
        assert "测试警告" in content

    def test_ui_bridge(self):
        """UI 桥接——set_log_func 应能将日志转发到 UI 面板。"""
        captured = []

        def ui_handler(msg):
            captured.append(msg)

        set_log_func(ui_handler)
        log("UI 测试消息")

        assert len(captured) == 1
        assert "UI 测试消息" in captured[0]

    def test_legacy_log_still_works(self):
        """旧 log() 接口应保持兼容。"""
        captured = []

        def ui_handler(msg):
            captured.append(msg)

        set_log_func(ui_handler)
        log("旧接口测试")
        assert len(captured) >= 1

    def test_module_name_in_log(self, log_dir):
        """日志应包含模块名，方便排查。"""
        setup_logging(log_dir=log_dir, level=logging.DEBUG, reset=True)
        logger = get_logger("test_module")

        logger.info("模块标识测试")

        for handler in logging.getLogger().handlers:
            handler.flush()

        log_files = list(log_dir.glob("*.log"))
        assert log_files, f"未找到日志文件: {list(log_dir.iterdir())}"
        content = log_files[0].read_text(encoding='utf-8')
        assert "test_module" in content

    def test_timestamp_in_log(self, log_dir):
        """日志应包含时间戳。"""
        setup_logging(log_dir=log_dir, level=logging.INFO, reset=True)
        logger = get_logger("test_time")

        logger.info("时间戳测试")

        for handler in logging.getLogger().handlers:
            handler.flush()

        log_files = list(log_dir.glob("*.log"))
        assert log_files, f"未找到日志文件: {list(log_dir.iterdir())}"
        content = log_files[0].read_text(encoding='utf-8')
        # 应包含 ISO 日期格式
        import re
        assert re.search(r'\d{4}-\d{2}-\d{2}', content), f"无时间戳: {content[:100]}"

    def test_log_rotation(self, log_dir):
        """日志文件应支持按大小滚动，不无限增长。"""
        setup_logging(log_dir=log_dir, level=logging.DEBUG, max_bytes=1024, backup_count=2, reset=True)
        logger = get_logger("test_rotation")

        # 写入大量日志触发滚动
        for i in range(200):
            logger.info(f"行 {i:04d} " + "x" * 100)

        # 关闭 handler 确保落盘
        for handler in logging.getLogger().handlers[:]:
            handler.flush()
            handler.close()
            logging.getLogger().removeHandler(handler)

        # 必须真实发生滚动：主文件 + 至少一个 .log.1 备份
        assert (log_dir / "app.log").exists(), f"主日志文件缺失: {list(log_dir.iterdir())}"
        assert (log_dir / "app.log.1").exists(), \
            f"滚动备份缺失（滚动未发生）: {list(log_dir.iterdir())}"
