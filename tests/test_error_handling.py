"""Issue 012：错误处理分层 + 指数退避 + 熔断器测试

验证异常层级定义、分类重试策略和熔断机制。
"""
import time
import pytest
import requests as req_mod
from unittest.mock import patch, MagicMock

from core.api_client import (
    ProofreadError,
    APITimeoutError,
    APIRateLimitError,
    APIAuthError,
    APIBadRequestError,
    FormatError,
    ToolExecutionError,
    _classify_error,
    _should_retry,
    _backoff_delay,
    _model_supports_reasoning_effort,
    _model_supports_images,
    call_api,
    StopReason,
    MAX_RETRY,
)


class TestErrorHierarchy:
    """验证异常层级定义。"""

    def test_base_error_is_exception(self):
        """ProofreadError 应继承 Exception。"""
        assert issubclass(ProofreadError, Exception)

    def test_subclass_relationships(self):
        """各子类应正确继承 ProofreadError。"""
        assert issubclass(APITimeoutError, ProofreadError)
        assert issubclass(APIRateLimitError, ProofreadError)
        assert issubclass(APIAuthError, ProofreadError)
        assert issubclass(APIBadRequestError, ProofreadError)
        assert issubclass(FormatError, ProofreadError)
        assert issubclass(ToolExecutionError, ProofreadError)

    def test_error_instantiation_with_message(self):
        """异常应携带消息和状态码。"""
        err = APITimeoutError("请求超时", status_code=504)
        assert str(err) == "请求超时"
        assert err.status_code == 504

        err2 = APIRateLimitError("请求过于频繁", status_code=429, retry_after=30)
        assert err2.retry_after == 30

        err3 = APIAuthError("认证失败", status_code=401)
        assert err3.status_code == 401
        assert not getattr(err3, 'retryable', True)  # 默认不可重试


class TestErrorClassification:
    """验证错误分类逻辑。"""

    def test_classify_timeout(self):
        """requests.Timeout → APITimeoutError。"""
        exc = req_mod.exceptions.Timeout("Connection timed out")
        proof_err = _classify_error(exc)
        assert isinstance(proof_err, APITimeoutError)

    def test_classify_connection_error(self):
        """requests.ConnectionError → APITimeoutError。"""
        exc = req_mod.exceptions.ConnectionError("Connection refused")
        proof_err = _classify_error(exc)
        assert isinstance(proof_err, APITimeoutError)

    def test_classify_http_429(self):
        """HTTP 429 → APIRateLimitError。"""
        resp = MagicMock()
        resp.status_code = 429
        resp.text = "Rate limit exceeded"
        exc = req_mod.exceptions.HTTPError(response=resp)
        proof_err = _classify_error(exc)
        assert isinstance(proof_err, APIRateLimitError)

    def test_classify_http_401(self):
        """HTTP 401 → APIAuthError。"""
        resp = MagicMock()
        resp.status_code = 401
        resp.text = "Unauthorized"
        exc = req_mod.exceptions.HTTPError(response=resp)
        proof_err = _classify_error(exc)
        assert isinstance(proof_err, APIAuthError)

    def test_classify_http_403(self):
        """HTTP 403 → APIAuthError。"""
        resp = MagicMock()
        resp.status_code = 403
        resp.text = "Forbidden"
        exc = req_mod.exceptions.HTTPError(response=resp)
        proof_err = _classify_error(exc)
        assert isinstance(proof_err, APIAuthError)

    def test_classify_http_400(self):
        """HTTP 400 → APIBadRequestError（不可重试）。"""
        resp = MagicMock()
        resp.status_code = 400
        resp.text = '{"error": "Invalid model or parameter"}'
        exc = req_mod.exceptions.HTTPError(response=resp)
        proof_err = _classify_error(exc)
        assert isinstance(proof_err, APIBadRequestError)
        assert proof_err.status_code == 400

    def test_classify_http_500(self):
        """HTTP 500 → 通用 ProofreadError（应可重试）。"""
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "Internal Server Error"
        exc = req_mod.exceptions.HTTPError(response=resp)
        proof_err = _classify_error(exc)
        assert isinstance(proof_err, ProofreadError)
        assert not isinstance(proof_err, (APITimeoutError, APIRateLimitError, APIAuthError))

    def test_classify_unknown_exception(self):
        """未知异常 → 通用 ProofreadError。"""
        exc = ValueError("unexpected error")
        proof_err = _classify_error(exc)
        assert isinstance(proof_err, ProofreadError)


class TestRetryStrategy:
    """验证重试策略。"""

    def test_timeout_is_retryable(self):
        """超时错误应为可重试。"""
        err = APITimeoutError("timeout")
        assert _should_retry(err) is True

    def test_rate_limit_is_retryable(self):
        """限流错误应为可重试。"""
        err = APIRateLimitError("rate limit")
        assert _should_retry(err) is True

    def test_auth_error_not_retryable(self):
        """认证错误不应重试。"""
        err = APIAuthError("unauthorized")
        assert _should_retry(err) is False

    def test_bad_request_not_retryable(self):
        """HTTP 400 错误不应重试——请求本身有问题。"""
        err = APIBadRequestError("bad request")
        assert _should_retry(err) is False

    def test_generic_proofread_error_is_retryable(self):
        """通用校对错误默认可重试。"""
        err = ProofreadError("generic error")
        assert _should_retry(err) is True


class TestBackoffDelay:
    """验证指数退避延迟。"""

    def test_backoff_increases_exponentially(self):
        """退避延迟应指数增长。"""
        d0 = _backoff_delay(0, base=2.0)
        d1 = _backoff_delay(1, base=2.0)
        d2 = _backoff_delay(2, base=2.0)
        assert d0 == pytest.approx(2.0)
        assert d1 == pytest.approx(4.0)
        assert d2 == pytest.approx(8.0)

    def test_backoff_has_max_cap(self):
        """退避延迟应有上限。"""
        d = _backoff_delay(10, base=2.0, max_delay=30)
        assert d == 30.0

    def test_rate_limit_longer_base(self):
        """限流错误应有更长的退避基准。"""
        err = APIRateLimitError("rate limit")
        d0 = _backoff_delay(0, base=err.backoff_base)
        assert d0 >= 5.0  # 限流基准至少 5 秒


class TestCircuitBreakerInCallApi:
    """验证 call_api 中的熔断器行为。"""

    @patch("core.api_client.requests.post")
    @patch("core.api_client._dump_initial_payload")
    @patch("core.api_client._save_conversation_log")
    def test_auth_error_stops_immediately(self, mock_save, mock_dump, mock_post):
        """认证错误应立刻停止，不重试，给出明确错误信息。"""
        mock_dump.return_value = ""
        mock_post.side_effect = req_mod.exceptions.HTTPError(
            response=MagicMock(status_code=401, text="Unauthorized")
        )

        result = call_api(
            api_url="http://test/v1",
            api_key="bad-key",
            model="test-model",
            md_text="测试文本",
            images=[],
            q_title="第1题",
            system_prompt="prompt",
        )

        assert result["stop_reason"] == StopReason.ERROR
        assert "认证失败" in result["content"] or "401" in result["content"]

    @patch("core.api_client.requests.post")
    @patch("core.api_client._dump_initial_payload")
    @patch("core.api_client._save_conversation_log")
    def test_timeout_retries_with_backoff(self, mock_save, mock_dump, mock_post):
        """超时错误应重试（指数退避）。"""
        mock_dump.return_value = ""
        mock_post.side_effect = req_mod.exceptions.Timeout("timeout")

        start = time.time()
        result = call_api(
            api_url="http://test/v1",
            api_key="key",
            model="test-model",
            md_text="测试文本",
            images=[],
            q_title="第1题",
            system_prompt="prompt",
        )
        elapsed = time.time() - start

        # 应该有重试延迟（至少 retry 次 sleep）
        # MAX_RETRY=2 → 尝试 3 次（初始 + 2 次重试），退避 2s + 4s = 6s
        assert elapsed >= 5.0, f"应有退避延迟，实际耗时 {elapsed:.1f}s"
        assert result["stop_reason"] == StopReason.ERROR

    @patch("core.api_client.requests.post")
    @patch("core.api_client._dump_initial_payload")
    @patch("core.api_client._save_conversation_log")
    def test_circuit_breaker_consecutive_same_error(self, mock_save, mock_dump, mock_post):
        """连续相同类型错误应触发熔断，不无限重试。"""
        mock_dump.return_value = ""
        mock_post.side_effect = req_mod.exceptions.Timeout("timeout")

        result = call_api(
            api_url="http://test/v1",
            api_key="key",
            model="test-model",
            md_text="测试文本",
            images=[],
            q_title="第1题",
            system_prompt="prompt",
        )

        # 重试次数不超过 MAX_RETRY
        call_count = mock_post.call_count
        assert call_count <= MAX_RETRY + 1, f"重试次数 {call_count} 不应超过 MAX_RETRY+1={MAX_RETRY+1}"
        assert result["stop_reason"] == StopReason.ERROR

    @patch("core.api_client.requests.post")
    @patch("core.api_client._dump_initial_payload")
    @patch("core.api_client._save_conversation_log")
    def test_bad_request_stops_immediately(self, mock_save, mock_dump, mock_post):
        """HTTP 400 错误应立即停止，不重试，不触发熔断。"""
        mock_dump.return_value = ""
        mock_post.side_effect = req_mod.exceptions.HTTPError(
            response=MagicMock(status_code=400, text='{"error": "Invalid parameter"}')
        )

        result = call_api(
            api_url="http://test/v1",
            api_key="key",
            model="test-model",
            md_text="测试文本",
            images=[],
            q_title="第1题",
            system_prompt="prompt",
        )

        # 400 不可重试 → 只调用 1 次
        assert mock_post.call_count == 1, f"400 错误不应重试，实际调用 {mock_post.call_count} 次"
        assert result["stop_reason"] == StopReason.ERROR
        assert "请求格式错误" in result["content"] or "400" in result["content"]

    @patch("core.api_client.requests.post")
    @patch("core.api_client._dump_initial_payload")
    @patch("core.api_client._save_conversation_log")
    def test_400_error_includes_response_body(self, mock_save, mock_dump, mock_post):
        """400 错误的响应体应出现在错误消息中。"""
        mock_dump.return_value = ""
        mock_post.side_effect = req_mod.exceptions.HTTPError(
            response=MagicMock(status_code=400, text='{"error": "Unsupported parameter: reasoning_effort"}')
        )

        result = call_api(
            api_url="http://test/v1",
            api_key="key",
            model="test-model",
            md_text="测试文本",
            images=[],
            q_title="第1题",
            system_prompt="prompt",
        )

        assert "Unsupported parameter" in result["content"], \
            f"响应体应出现在错误消息中，实际: {result['content'][:200]}"


class TestModelReasoningEffortSupport:
    """验证 _model_supports_reasoning_effort 的模型兼容性判断。"""

    def test_deepseek_reasoner_supports(self):
        """deepseek-reasoner 支持 reasoning_effort。"""
        assert _model_supports_reasoning_effort("deepseek-reasoner") is True

    def test_deepseek_chat_not_support(self):
        """deepseek-chat (V3) 不支持 reasoning_effort。"""
        assert _model_supports_reasoning_effort("deepseek-chat") is False

    def test_deepseek_v4_pro_supports(self):
        """deepseek-v4-pro 是推理模型，支持 reasoning_effort。"""
        assert _model_supports_reasoning_effort("deepseek-v4-pro") is True

    def test_doubao_supports(self):
        """豆包模型默认返回 True（忽略未知参数，无害）。"""
        assert _model_supports_reasoning_effort("doubao-seed-2-0-pro-260215") is True

    def test_unknown_model_defaults_true(self):
        """未知模型默认发送（绝大多数 API 忽略未知参数）。"""
        assert _model_supports_reasoning_effort("gpt-4o") is True
        assert _model_supports_reasoning_effort("claude-3-opus") is True


class TestModelImageSupport:
    """验证 _model_supports_images 的图片兼容性判断。"""

    def test_deepseek_v4_pro_text_only(self):
        """deepseek-v4-pro 是纯文本模型，不支持图片。"""
        assert _model_supports_images("deepseek-v4-pro") is False

    def test_deepseek_reasoner_text_only(self):
        """deepseek-reasoner (R1) 是纯文本推理模型。"""
        assert _model_supports_images("deepseek-reasoner") is False

    def test_deepseek_chat_supports_images(self):
        """deepseek-chat (V3) 支持多模态/图片。"""
        assert _model_supports_images("deepseek-chat") is True

    def test_doubao_supports_images(self):
        """豆包模型默认支持图片。"""
        assert _model_supports_images("doubao-seed-2-0-pro-260215") is True

    def test_unknown_model_defaults_true(self):
        """未知模型默认支持图片。"""
        assert _model_supports_images("gpt-4o") is True
