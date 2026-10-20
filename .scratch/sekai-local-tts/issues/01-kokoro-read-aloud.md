Status: done

## 目标

TOL-278 用户要求轻量 TTS 替代语音生成并安装模型。在已有 v0.1.2 私人 HTTPS/Whisper 输入基础上新增真正的离线回复朗读。基点26db0d68f8aaf270a599d26a9b07f5f001165b73。只做本票应用实现；root 负责权重下载、Compose、生产部署、整体验收、字体与最终提交。

## 验收

- [x] 独立 `deploy/sekai/tts/` Python3.11服务、uv.lock和Dockerfile，使用 kokoro-onnx==0.6.1、misaki==0.9.4 的中日G2P，无torch/GPU。模型为 Kokoro v1.0 int8，路径 `/models/kokoro-v1.0.int8.onnx`、`/models/voices-v1.0.bin`。日语使用官方 `misaki.cutlet.Cutlet()` 与预装 `unidic-lite==1.0.8` 精简词典，中文 `zh.ZHG2P()` 使用v1.0；日语jf_alpha、中文zf_xiaobei。需要的misaki基础包和zh依赖，以及fugashi==1.5.2、jaconv==0.5.0、mojimoji==0.0.13锁定；不装misaki[ja]/[en]、完整unidic、pyopenjtalk或torch/spacy。词典随镜像预装，服务启动先检查词典与模型文件，禁止运行时自动下载。jieba缓存只在/tmp，服务预热可公开固定文本，不记录用户文字/phonemes。
- [x] 显式 ONNX CPUExecutionProvider、4线程，启动只加载本地权重，GET /health ready。POST /synthesize 接收小型JSON `{text,language:'ja'|'zh-cn'}`，流式有界最多4096bytes/15秒、严格字段/字符/编码长度界限；最长300字，音素总量/分段/60秒音频上限明确；在真实worker内持有全局锁至结束，单并发满时429不建立无界队列；原生推理无法强制取消需文档说明安全重启。输出24kHz单声道PCM16 WAV，有限/非空/数值有限校验，无磁盘音频和文本日志，安全错误、no-store。与Whisper类似只部署内网、非root/只读镜像。
- [x] 主后端新管理员 `EIDOLON_LOCAL_TTS_URL` 校验同Whisper URL；`read_aloud_api.py` 优先使用已配置本地TTS，不回退火山。复用私人认证/consent/Origin/owned_message，只接受现有会话消息ID，ja优先否则中文，去delivery cues，有界text。httpx trust_env=False、响应类型/PCM WAV头与大小验证、超时、safe errors、abort disconnect；返回audio/wav。保留原火山逻辑用于旧配置，未配置本地时原有测试保持兼容。availability async检查真实健康，给provider/languages等准确元数据；本地朗读不可用不误报火山缺密钥。
- [x] 恢复现有点击朗读入口，单条点击播放、停止、取消、Safari手势恢复沿用已有控制器。准确展示「本地合成音色，非官方角色声音」；不自动朗读历史消息、不做完整电话。版本v0.1.3，更新consent/privacy/terms/work文案，讲清Whisper录音本地、点击朗读文字本地、聊天LLM仍外部，别声称克隆了Miku。日/中文支持准确；本地服务未就绪显示对应提示，不是火山配置提示。
- [x] 重点定向测试：本地配置校验、鉴权/拥有权/关闭开关、ready/失败、正确语言/WAV、安全有界返回/no fallback、并发/取消；侧车纯mock验证限额/锁/WAV与断网启动条件。现有前端逻辑测试必要处更新，控制器本身无不必要重构。

## Testing Decisions

读AGENTS.md、docs/agents/implementing.md、frontend/AGENTS.md相关Next本地指南；使用python-coding-guidelines和typescript技能。定向pytest/vitest、Ruff、py_compile、模块Pyright及typecheck。不要跑affected-tests、next build、Playwright或字体子集，不提交不推送，不读取密钥或用户消息。root统一两份独立review、生产验证和提交。

## 资料

https://github.com/thewh1teagle/kokoro-onnx （from_session明确CPU线程，is_phonemes=True）
https://github.com/hexgrad/misaki （misaki.cutlet.Cutlet / zh.ZHG2P v1.0）
https://huggingface.co/hexgrad/Kokoro-82M （Apache2.0权重，非Miku声纹）

## Comments

root负责模型下载与校验。官方v1.0 release int8文件92361271bytes，voices28214398bytes，地址为github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/。原前端朗读支持Blob格式，无需固定mpeg。


### 实现说明（票 01）

应用实现已完成，等待 root 的两份独立审查、真实断网验收及最终关票/提交。

- 新增 `deploy/sekai/tts/{server.py,pyproject.toml,uv.lock,Dockerfile,README.md}`。锁定 Kokoro ONNX 0.6.1、Misaki 0.9.4、pyopenjtalk 0.4.1、ONNX Runtime 1.23.2；Docker 多阶段编译 pyopenjtalk，运行镜像无编译链、torch 或 GPU。模型与词典路径遵循票定义。`GET /health` 和 `POST /synthesize` 使用票内接口，24kHz mono PCM16 WAV。
- 按 PyPI wheel 源码确认 Misaki 0.9.4 的 pyopenjtalk 分支返回 `result + pitch`：附加音高轨等长且仅含 `_^-j`。v1.0 适配先校验形态再移除附加轨，避免其 `j` 被读成尾音；预热和正式合成都用同一适配。
- 后端新增 `local_tts.py`，`Settings.local_tts_url` 读取 `EIDOLON_LOCAL_TTS_URL`，校验同 Whisper。保存消息鉴权、consent、Origin 与拥有权均沿用已有入口；配置本地后只调用该服务，不回退火山。异步健康状态含 provider/languages/voices；严格验证有界 canonical PCM WAV，不回显侧车错误，关闭环境代理与重定向。
- 保留播放控制器及 Safari 手势恢复，前端区分本地未就绪和火山待配置；现有点击入口自动恢复。更新 v0.1.3、consent/privacy/terms/work，明确本地录音识别、本地点击朗读、外部聊天模型及非官方合成音色。
- 定向测试覆盖后端配置/健康/故障/无云回退/语言/WAV/关闭与取消、侧车输入/音素/音频边界、缺本地文件、并发锁和取消、前端状态与原控制器。已通过后端 64、侧车 27、前端 16 个测试；后端修改模块 Pyright、Ruff、py_compile 和前端 typecheck 通过。最终验证记录由 root 汇总。
- 明确限制：原生 ONNX 单次推理不可强制取消，HTTP 取消/超时后实际线程仍持有单并发锁；必要时由部署者安全重启 TTS 容器。此限制已写入 README。

```json
{"ticket":"01-kokoro-read-aloud","implementation":"complete","delivery":"awaiting_root_review_and_acceptance","api":{"health":"GET /health","synthesis":"POST /synthesize","languages":["ja","zh-cn"],"voices":{"ja":"jf_alpha","zh-cn":"zf_xiaobei"},"output":"audio/wav; PCM16 mono 24000Hz"},"limits":{"request_bytes":4096,"text_characters":300,"text_utf8_bytes":1200,"phonemes":2400,"chunk_phonemes":400,"chunks":12,"audio_seconds":60},"tests":{"backend":64,"sidecar":27,"frontend":16},"remaining_owner":"root","remaining":["independent_reviews","font_subset","compose_and_deployment","offline_cpu_acceptance","commit_and_push"]}
```

### 两份独立审查（root汇总）

两份code-review报告均已返回：日语pyopenjtalk音素与Kokoro v1.0词表不兼容为Major；独立probe完整差集为G K g ƫ ᶀ ᶁ ᶃ ᶄ ᶆ ᶈ ᶉ，不能仅修g和ᶄ。已剥pitch仍会静默丢词。另有原文每60字切分会割裂今日等词语的Minor；UI首次unready无重试、中文兜底没有使用Message.zh且按钮只看ja，两项Major。无Critical，认证/拥有权、无云回退、WAV界限、实际worker锁及内网资源隔离通过。

决策：改用Misaki官方Cutlet v1.0前端，锁定fugashi1.5.2、unidic-lite1.0.8（词典随包预装，不启动下载）、jaconv0.5.0、mojimoji0.0.13；不安装unidic完整包，移除不再使用的pyopenjtalk/OpenJTalk运行依赖。完整有界300字先G2P，再按音素窗处理，并在推理前对词表全覆盖检查，未知音素安全拒绝而不是删除。补公开kana/拗音/跨60字今日回归与真实固定句验证。后端以去cue后实际非空ja→zh→legacy text选语言；前端中文也显示按钮；增加显式重试健康探测。root在票02结束后串行交回原实现代理修复。


### 审查修复（票 01）

两份审查汇总提出的应用问题已修复：日语改为 Misaki 官方 Cutlet 与随镜像预装的 unidic-lite 精简词典，移除 pyopenjtalk、OpenJTalk 和旧音高轨适配；Docker 不再需要编译工具。完整 <=300 字回复只做一次 G2P，再分 400 音素窗；预热与正式路径共享严格词表检查，空或未知音素返回安全 422，防止 Kokoro 静默丢字。真实 G2P 的假名、拗音、跨原 60 字边界「今日」与中文固定句 8 项回归通过，无需 ONNX 权重。

后端现在按去 cue 后实际非空的 ja → zh → legacy text 选择文字及语言；增加空白、cue-only 日文和中文优先回归。中文回复显示朗读按钮。初次 unready 或探测失败时展示「重试朗读连接」，点击立即取消旧健康请求并重新探测；离页与账户变化也取消旧请求，没有后台轮询。保留原播放控制器。

当前定向结果：后端 read_aloud/local_tts 48 tests，侧车边界及真实 G2P 38 tests，前端 17 tests；Ruff、后端模块 Pyright、py_compile 与前端 typecheck 通过。root 继续最终镜像断网验收及关闭票。

```json
{"review_fixes":"complete","japanese_g2p":"misaki.cutlet.Cutlet + fugashi1.5.2 + unidic-lite1.0.8 + jaconv0.5.0 + mojimoji0.0.13","removed":["pyopenjtalk","OpenJTalk","pitch_track_adapter","text_60_character_splitting"],"regressions":{"backend":48,"sidecar":38,"frontend":17},"healthy_retry":"explicit_abort_previous_no_polling","next_owner":"root"}
```

### root 生产交付

v0.1.3 已在原HTTPS地址上线，六容器健康，原1账户/1会话/14消息保留。真实断网Kokoro生成中日公开句，Whisper回转与原文忽略标点后相符。HTTPS真实消息朗读成功、CPU4线程且无外网端口；浏览器验证真实WAV播放/停止、显式健康重试、真实Miku模型渲染/动作、关闭释放WebGL、移动端/减少动态效果/故障静态回退。测试没有发送聊天消息，没有外部浏览器资源请求。原生推理取消限制、Safari和物理麦克风真机仍按文档保留为人工体验项。最终本地177后端/580前端/38TTS服务测试、类型与纪律、生产构建通过；快照恢复到临时库验证通过。root接续提交推送及PR交付。
