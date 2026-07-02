# Issue 012：错误处理分层 + 指数退避 + 熔断器

## Parent

ADR-0012（框架工程债识别与修复路线）— 问题 3：错误处理无分层

## What to build

为校对流程建立分层错误处理体系，替换当前所有异常统一 `try/except` + `log(msg)` 的粗放模式。

**问题**：
- API 超时 vs 格式错误 vs 工具异常 → 全部走同一条处理路径，无法区分对待
- `MAX_RETRY=2` + `time.sleep(2)` → 无指数退避，API 短暂过载时仍快速重试
- 无熔断器 → 连续失败仍逐个重试，浪费 API 额度

**修复方向**：
1. 定义异常层级：
   ```
   ProofreadError（基类）
   ├── APITimeoutError      → 可重试，指数退避
   ├── APIRateLimitError    → 可重试，更长退避
   ├── APIAuthError         → 不可重试，立即提示用户
   ├── FormatError          → 触发格式修正（_llm_format_fix）
   └── ToolExecutionError   → 记录后继续，不中断流程
   ```
2. 重试策略：指数退避（2s → 4s → 8s），带最大延迟上限
3. 熔断器：连续 3 次同类型失败 → 停止后续重试，输出明确诊断信息

**涉及文件**：
- `core/api_client.py` — 异常定义 + 重试逻辑 + 熔断器
- `core/defaults.py` — 接入分层错误处理

## Acceptance criteria

- [ ] 定义 `ProofreadError` 异常层级，至少包含上述 5 种类型
- [ ] API 超时/限流使用指数退避重试（2s → 4s → 8s，上限 30s）
- [ ] 认证错误立即停止，不重试，给出明确用户提示
- [ ] 连续 3 次同类型失败触发熔断，日志输出完整错误链
- [ ] 现有校对流程不受影响，正常路径无回归

## Blocked by

None - 可立即开始
