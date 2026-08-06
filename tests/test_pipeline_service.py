"""测试 core/pipeline_service.py 服务编排（ADR-0022 C3）。

⚠️ 契约测试说明：
ConversionService.run_conversion 与 ProofreadService.run_proofread 当前为
**骨架实现**（完整业务逻辑需从 ui/default_app 逐段搬迁，源码注释自述）。
本文件测试锁定「骨架阶段真实存在的行为」——接口形状、中断检测、目录存在
检查、题目目录扫描——并在各测试上标注业务搬迁后必须替换/补强的断言。
不得在骨架阶段用 success=True 为未实现的校对行为背书。
"""
import tempfile
import threading
from pathlib import Path

from core.pipeline_service import (
    ConversionRequest,
    ConversionResult,
    ConversionService,
    ProofreadRequest,
    ProofreadService,
)


class TestConversionService:
    """接口契约锁定（业务搬迁后需替换为真实转换断言）。"""

    def test_returns_result_shape(self):
        """契约：入参出参类型与中断语义不变"""
        svc = ConversionService()
        req = ConversionRequest(md_file="/tmp/test.md", output_root="/tmp/out")
        result = svc.run_conversion(req)
        assert isinstance(result, ConversionResult)
        # 骨架阶段：不检查文件存在性、不做转换——仅锁接口形状
        # TODO(搬迁后): 断言真实转换产物（md 拆分结果、批注回写）

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
        """锁定真实已实现部分：目录扫描 + 计数组装。

        注意：completed == total 是骨架 TODO 行为（未做任何实际校对）；
        业务搬迁后此断言必须改为 completed == 实际完成数。
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "第1题").mkdir()
            svc = ProofreadService()
            result = svc.run_proofread(ProofreadRequest(
                api_url="", api_key="", model="", paper_dir=td,
            ))
            # 真实扫描逻辑（scan_question_dirs）：识别 1 个校对单元
            assert result.total_questions == 1
            # TODO(搬迁后): 断言 completed == 实际校对完成数，并 mock 校对执行

    def test_subject_app_field_is_dataclass_field(self):
        """回归：subject_app 是 dataclass 字段（此前无类型注解被忽略，传入即 TypeError）"""
        import dataclasses

        from core.pipeline_service import ProofreadRequest
        field_names = {f.name for f in dataclasses.fields(ProofreadRequest)}
        assert "subject_app" in field_names
        req = ProofreadRequest(api_url="u", api_key="k", model="m",
                               paper_dir="/tmp", subject_app=object())
        assert req.subject_app is not None

    def test_interruption(self):
        evt = threading.Event()
        evt.set()
        svc = ProofreadService(interrupt_event=evt)
        result = svc.run_proofread(ProofreadRequest(
            api_url="", api_key="", model="", paper_dir="/tmp",
        ))
        assert not result.success
        assert "中断" in result.error
