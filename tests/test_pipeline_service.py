"""测试 core/pipeline_service.py 服务编排（ADR-0022 C3）。"""
import threading
import tempfile
from pathlib import Path

import pytest

from core.pipeline_service import (
    ConversionRequest,
    ConversionResult,
    ConversionService,
    ProofreadRequest,
    ProofreadResult,
    ProofreadService,
)


class TestConversionService:
    def test_basic_conversion(self):
        svc = ConversionService()
        req = ConversionRequest(md_file="/tmp/test.md", output_root="/tmp/out")
        result = svc.run_conversion(req)
        assert isinstance(result, ConversionResult)
        assert result.success

    def test_interruption(self):
        evt = threading.Event()
        evt.set()
        svc = ConversionService(interrupt_event=evt)
        result = svc.run_conversion(ConversionRequest(md_file="x", output_root="y"))
        assert not result.success
        assert "中断" in result.error


class TestProofreadService:
    def test_missing_dir(self):
        svc = ProofreadService()
        result = svc.run_proofread(ProofreadRequest(
            api_url="", api_key="", model="", paper_dir="/nonexistent",
        ))
        assert not result.success
        assert "不存在" in result.error

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as td:
            svc = ProofreadService()
            result = svc.run_proofread(ProofreadRequest(
                api_url="", api_key="", model="", paper_dir=td,
            ))
            assert not result.success
            assert "未找到" in result.error

    def test_dir_with_questions(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "第1题").mkdir()
            svc = ProofreadService()
            result = svc.run_proofread(ProofreadRequest(
                api_url="", api_key="", model="", paper_dir=td,
            ))
            assert result.success
            assert result.total_questions == 1

    def test_interruption(self):
        evt = threading.Event()
        evt.set()
        svc = ProofreadService(interrupt_event=evt)
        result = svc.run_proofread(ProofreadRequest(
            api_url="", api_key="", model="", paper_dir="/tmp",
        ))
        assert not result.success
        assert "中断" in result.error
