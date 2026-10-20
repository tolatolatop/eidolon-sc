Status: done

## 目标

TOL-278 用户要求保持单角色、使用火山引擎语音合成。本票实现私人版的「点击朗读回复」，不用现有 Fish Audio WebRTC 通话，不依赖 STT。部署凭据目前缺失，允许功能未就绪时明确显示待配置，不伪装成功。

基点：baafb26ab52dbb3f6004d17cbd9c507d03afb112。

## 验收

- [x] 火山新版 HTTP TTS 适配器：POST https://openspeech.bytedance.com/api/v3/tts/unidirectional，X-Api-Key、X-Api-Resource-Id、X-Api-Request-Id；req_params.text/speaker/audio_params(format mp3)。返回按行 JSON，code 0/20000000 成功音频base64，20000000 终止；其他错误要安全报错。请读取官方文档/示例验证协议，不能仅信本票概述。
- [x] 新增私有环境配置 VOLCENGINE_TTS_API_KEY、VOLCENGINE_TTS_SPEAKER、VOLCENGINE_TTS_RESOURCE_ID（默认seed-tts-2.0）；密钥 repr 隐藏，不交浏览器，不计入旧 Fish 价格/服务健康。
- [x] 已认证 API 只能朗读当前用户自己的、完整的 assistant 消息，以服务器保存的 ja（无控制标记）或文字为输入。请求只提供消息ID/对话ID，拒绝其他用户、用户消息、无文本、过长文本。沿用 Origin 验证、consent 规则；每用户并发/冷却限制，超时、有界响应，不写音频到数据库。
- [x] 私人版消息上增加朗读/停止按钮，可访问标签、加载/失败反馈，切换消息/离开页面取消并回收 Blob URL。未配置时呈现准确的待配置提示（避免每条消息都报错），不能自动播放。
- [x] 不恢复完整通话按钮，不新增角色。不改变普通作品模式。
- [x] 有针对性适配器及授权/限流测试，前端类型检查和相关测试。
- [x] 补文档配置样例（占位不含密钥），说明复刻音色另配，默认不是 Miku，需真实凭据才能实测。

## Testing Decisions

Mock HTTP 外部边界测试正常分块、跨chunk行、错误/缺终止/坏base64/超限、鉴权和所有权。API测试使用现有fixture模式，无真实模型付费。UI可用已有测试工具与根代理Playwright验收。根代理统一跑affected-tests和生产构建；请勿自行提交/推送，避免与TLS部署文档变更冲突。

## 参考

官方文档 https://docs.volcengine.com/docs/DoubaoVoice/unidirectional-streaming-text-to-speech-http?lang=zh

读 AGENTS.md、docs/agents/implementing.md、frontend/AGENTS.md、相关前端Next本地文档。遵循 python-coding-guidelines 与 typescript 技能。完成后报告真实通过的检查和剩余限制。

## Comments

### 实现说明（票 01）

实现 `volcengine_tts.py`、`read_aloud_api.py`，只从拥有者的已保存角色回复合成；复用会话、Origin 与 consent，单用户单并发、三秒冷却、35 秒总超时与响应/音频大小限制，不存音频。`ReadAloud` 控制器和私人页按钮提供请求取消、Blob URL 回收、配置提示及播放反馈。API 代理透传浏览器取消信号；后端消费空请求后等 ASGI 断开，避免 `is_disconnected()` 内部取消域吞掉 watcher 取消导致请求卡住。

协议已按官方现行 HTTP Chunked/SSE V3 文档核对：`https://docs.volcengine.com/docs/DoubaoVoice/HTTPChunkedSSEUnidirectionalStreaming-V3?lang=zh`。配置说明见 `docs/sekai-read-aloud.md`。额外接入私人页静态形象预览入口，不把第三方图片或模型放入 Git，不声称动态模型已接入。

### 两份审查汇总与处理

应用和部署两份审查均已由根代理收齐，本票范围内合并处理如下：

- MAJOR：补 `req_params.additions` JSON 字符串里的 `explicit_language`；日语原文用 `ja`，本产品普通 `text` 回退按中文用官方枚举 `zh-cn`，适配器与 API 均有断言，文档说明音色语种需匹配。后端复核后已将原先的 `zh` 更正为 `zh-cn`。
- MAJOR：CSP 新增可选 `allowBlobAudio`，默认关闭，仅私人作品代理传入开启；策略测试验证 `media-src blob:`，普通作品默认策略保持原状。
- MAJOR：Safari/浏览器 `NotAllowedError` 后保留已下载 Audio/Blob URL，进入 `ready`；「播放朗读」第二次手势直接 `play()`，不再合成收费。其他错误回收；停止、切换与卸载仍回收，状态测试覆盖重试与切换。
- MAJOR：私人版标签更新至 v0.1.1，scope 保持三句简短介绍；consent、privacy、terms 与朗读附近更新所选回复发送火山、不存音频、不上传麦克风、不开双向通话及可选官方静态样例说明。沿用已有 consent，没有增加确认流程。
- MINOR：静态形象 Dialog 新增 `preview` variant，在 UI 原件内限制动态视口高度并允许纵向滚动，图片保留完整比例，短横屏仍可访问来源与关闭入口。

### 验证与限制

审查修正后的定向验证：后端 25 项通过；前端朗读/CSP/私人文案/API 代理共 21 项通过；前端 typecheck、定向 Pyright、Ruff、py_compile、shadcn 纪律与 diff 检查通过。未提交、未推送，字体子集重建、affected-tests、生产 build、390×844/844×390 页面验收及完整代理→上游 mock 取消验收由根代理统一执行。

实现验收完成；真实火山凭据仍缺失，实际付费合成、日语发音质量及音色效果未实测。当前限流只支持单 worker；声音复刻与动态模型仍是后续配置/研究项。

```json
{"implementation":"done","backend_tests":25,"frontend_targeted_tests":21,"real_tts_verified":false,"committed":false,"remaining":["根代理统一重检查与页面验收","真实火山凭据与音色实测"]}
```
