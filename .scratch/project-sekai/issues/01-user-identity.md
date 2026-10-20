Type: prototype
Status: done

## 目标

TOL-278：让隔离的初音未来文字对话配置不再把用户认作 283 事务所男性制作人，同时保留原配置行为。

## 实现范围

- Character 增加可选的 `user_role` 和 `user_identity`（须同时配置、非空单行），分别表示用户在当下交流中的身份称谓和完整身份说明。不配置时保持旧行为。
- producer_prompt 与 now_prompt 支持该配置；自定义身份不默认假定男性，不再把自定义称呼解释为制作人身份。用户填写的性别、称呼、生日仍生效。
- Engine 在每个回合传入角色的上述配置。默认提示词行为保持兼容。
- 测试覆盖配置校验、旧配置兼容、自定义身份实际进入文字回合模型提示词；验证文字/通话时间和生日上下文。
- 不改前端、同步器、数据库、不更改原作角色资产。

## 验收

- [x] 自定义身份不包含 283 事务所或默认男性设定。
- [x] 原配置默认行为和现有针对性测试通过。
- [x] 新增配置验证和文字回合接线测试通过。

## Testing Decisions

使用现有 pytest fixtures 和 FakeLLM 在 API 文字回合边界验证实际提示词；外部模型不调用。执行 py_compile、ruff、pyright 和相关测试；完成后交主代理统一执行 affected-tests。详见 docs/agents/implementing.md。不要提交或推送；由主代理集成。

## Comments

基点：4f55fb03918dd0d59290181a8077c513f3bad488。此原型仅扩展当前身份上下文，不宣称全站术语已迁移。

### 实现说明（票 01）

- `Character` 增加可选 `user_role` / `user_identity`，必须成对提供非空单行字符串；拒绝非字符串、任意换行（含尾部换行），加载后去除首尾空格。
- `producer_prompt` 接收两个关键词参数，使用自定义身份和角色称谓；未填性别时不添加默认男性设定。用户档案中的称呼、性别、生日继续有效；未配置身份时旧提示词保持原样。
- `now_prompt` 接收 `user_role`，用于文字／通话状态、时区与生日祝福。`ConversationEngine` 每回合传入角色配置。
- 新增 `backend/tests/test_user_identity.py`，从真实文字 API 边界检查连续两个回合、性别选项、档案称呼、跨时区生日及角色间隔离，并覆盖文字／通话当前上下文与配置拒绝。
- `uv sync --locked` 成功，未改依赖或锁文件。`py_compile`、针对改动文件的 Ruff 与 Pyright 通过；`uv run pytest -q tests/test_user_identity.py tests/test_producer_profile.py tests/test_characters.py`：135 passed，2 个既有第三方弃用警告。
- 局限：照片、好感度等已有子系统仍可能使用制作人术语；此票未迁移全站术语，未验证真实模型输出或通话设备。主代理统一进行双份 code-review、affected-tests 与提交推送。

### 集成与审查

- 新增 `examples/project-sekai/`：教室世界初音、三幕原创练习、出处、独立数据库与本机启动步骤；API 配置集成测试通过。
- 两份独立 code-review 均发现开发登录默认监听全部网卡；已通过示例 `HOST=127.0.0.1`、启动命令的显式 HOST 与前端 `--hostname 127.0.0.1` 修复。未发现其他阻断问题。
- `sh scripts/affected-tests.sh 4f55fb03918dd0d59290181a8077c513f3bad488`：Ruff 和 Pyright 全项目通过，181 tests passed；2 个既有第三方弃用警告。py_compile、check-scratch 和 diff 检查通过。
- 后续 Multica 任务 TOL-280～282 位于 backlog，记录人工范围与授权确认、剧情与世界记忆隔离、前端与发布。没有启动任何公开服务，也没有修改原角色配置或现有数据库。
