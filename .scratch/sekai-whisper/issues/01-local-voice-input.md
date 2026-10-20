Status: done

## 目标

TOL-278 最新用户要求暂不用火山，改为普通本地 Whisper。Whisper 是语音识别，不是合成；主代理已说明并发出异步澄清，在回复前按本地录音转文字推进。本票实现端到端本地语音输入，不做角色语音合成，不增加角色。

基点：106f770c39047f97711eded1d0b27a63418d5ea0。

## 验收

勾选表示应用实现与定向 mock 边界验收已完成；真实模型、实际浏览器及生产部署验收仍由 root 接续，详见 Comments。

- [x] 独立本地 Whisper 服务代码放 deploy/sekai/whisper/，使用 faster-whisper 的 multilingual small、CPU int8、4线程；权重路径环境 WHISPER_MODEL_PATH 默认 /models/small，local_files_only=True。独立pyproject+uv.lock+Dockerfile，Python3.11，依赖版本锁定。权重不进镜像或Git。根代理负责模型下载和Compose部署，不要改compose主文件。
- [x] 服务 POST /transcribe 接收原始音频字节和 language=auto|zh|ja，输出text/language。GET /health 只在模型加载完成返回成功。音频仅内存，不落盘不日志记录内容，不外传。5MiB上限、解码后30秒硬上限、输出长度界限、静音VAD返回空结果、坏音频/非音频安全报错。不能直接用无界decode_audio读完全文件，需有界PyAV流式解码与16k单声道重采样。所有推理使用单一worker/全局锁，满时拒绝而不排无界队列。CPU解码推理离开ASGI事件循环；客户端取消不应提前释放仍在运行的推理锁。由Docker资源限制兜底，根代理设置4CPU/4GiB内存。
- [x] 主后端增加 EIDOLON_LOCAL_WHISPER_URL（管理员配置，无用户URL）、已认证 GET /api/voice-input readiness、POST /api/voice-input/transcribe 代理。private-only、UserId+consent+Origin、流式收body限制、音频MIME与语言白名单、并发/冷却、超时、有界响应，安全错误，绝不回退云服务、不保存音频。侧车只在Docker网内，不发布端口。不把API密钥传给侧车。
- [x] 私人版输入框增加「录音输入」，明确最多30秒，开始时才请求麦克风；停止转写、取消、计时上限。结果允许校对后「填入草稿」，不得自动发送，不能覆盖原有草稿（显式追加）；录音/转写取消、切换对话、离页、pending getUserMedia晚返回都释放tracks/abort/忽略迟到结果。支持Chrome webm+Safari mp4，权限拒绝/不支持浏览器/HTTPS未信任/服务未就绪要准确提示。
- [x] 本部署停用火山朗读：增加 EIDOLON_READ_ALOUD_ENABLED 默认true以保持旧模式兼容，主代理在部署设0。关闭时API不调用火山，availability明确enabled=false；前端隐藏原「朗读待配置」和按钮。历史源码保留以便回滚。不恢复电话入口。
- [x] 更新 PRIVATE_WORK v0.1.2、consent/privacy/terms、独立本地ASR配置说明。说明录音上传到本部署Whisper，暂存内存不保存；校对并点击发送的文字仍会由既有外部LLM处理。不要声称所有聊天已离线，也不要声称Whisper产生Miku音色。字体主代理统一更新。
- [x] 重点测试：鉴权/consent/Origin/输入和响应界限/服务错误不泄露；侧车解码超时长/静音/损坏/拒绝并发（mock模型）；前端录音状态/取消释放/迟到结果/不自动发送和草稿保护。CPU真实模型验收和生产浏览器由主代理完成。

## Testing Decisions

Mock网络、麦克风和模型边界；无需真实外部付费模型。服务单测独立pytest，主后端沿用现有fixtures，前端逻辑用既有vitest模式。不要跑affected-tests、next build、Playwright、字体子集；只做定向单测/typecheck/ruff/py_compile。不要提交或推送；主代理统一两份独立review后收尾。

## 资料

https://github.com/SYSTRAN/faster-whisper （CPU int8、PyAV、local_files_only、VAD）
https://github.com/openai/whisper （识别而非合成）

读AGENTS.md、docs/agents/implementing.md、frontend/AGENTS.md及Next本地指南；遵循python-coding-guidelines和typescript技能。只改本票应用与独立whisper目录；Compose、主部署README和handoff由主代理维护。不要读取真实密钥或改已有用户数据。

## Comments

### 实现说明（票 01）

已新增 `deploy/sekai/whisper/` 独立 Python3.11 侧车、精确依赖与 uv.lock、非 root 镜像及 .dockerignore；模型只读本地加载，CPU int8 四线程，不占 GPU。PyAV 按音频采样数限制30秒并禁用外部协议/非允许容器；实际工作线程持有全局锁至结束，取消 HTTP 不会提前释放锁。音频只存内存。

主后端新增 `voice_input_api.py` 和管理员地址设置：私人认证/consent/Origin、流式5MiB限制、白名单、单并发/冷却、有界响应与安全错误；浏览器中止会取消上游代理，不回退云识别。朗读开关关闭时先拒绝请求，前端不显示配置提示或朗读按钮。

新增 `VoiceRecorder` 与 `VoiceInput`，先录音再转写、校对后显式追加到草稿；2,000字合并上限超出时保留原草稿和识别文字。取消、页面离开、对话切换及晚到麦克风/识别结果均做清理。默认计时使用 `performance.now()`，保留 `VoiceInputDependencies.now` 注入接缝；29秒自动停止留出编码余量。界面明确要求录音时页面保持前台。

PRIVATE_WORK、consent/privacy/terms 已更新 v0.1.2，明确本地 ASR 与外部 LLM 的处理边界。

### 独立审查与处理

root 已汇总两份只读独立 review：均无阻塞问题。前端 MINOR（系统时钟回拨可能延长录音）已修为单调时钟，并新增回拨一小时仍按原计时停止的定向验证。页面挂起或设备休眠导致停止事件延迟属于剩余限制：界面要求保持前台，文档不承诺前端跨挂起绝对限时；服务器继续硬性拒绝超过30秒的解码音频。

后端 MINOR（原生解码/推理不能由 HTTP 超时强制中断）由 root 接受为私人部署残余限制；保留单实际 worker 锁、代理超时及 Docker CPU/内存限制。独立 README 已补卡住时仅 `docker compose restart whisper`，保留模型和数据卷，禁止用删除卷恢复。

### 定向验证与交接

- 主后端30项、侧车15项、前端原18项通过；单调时钟修复后录音测试8项通过（比原7项增加1项）。
- `npm run typecheck`、shadcn 纪律、Python ruff/py_compile、代理模块 pyright、`git diff --check` 通过。
- CPU small 真实模型、VAD、中日样本、实际 Chrome webm / Safari mp4、生产浏览器与最终部署检查由 root 待完成；本票未将 mock 通过表述为真实生产已验收。
- 未提交或推送；字体、Compose、主部署 README 和 handoff 由 root 统一维护。

```json
{"implementation":"done","reviews":{"count":2,"blocking":0,"clock_minor":"fixed","native_worker_minor":"accepted_with_documented_restart"},"verification":{"backend":30,"whisper":15,"frontend_before_clock_fix":18,"voice_input_after_clock_fix":8,"typecheck":"passed"},"root_pending":["real_cpu_small_and_vad","real_audio_samples","production_browser","final_deployment"],"committed":false,"pushed":false}
```

### root 最终验收

生产 v0.1.2 已部署至原 HTTPS 地址，五个容器健康。small 权重按固定 revision 和 SHA-256 校验，独立断网容器真实验证中日英语音、静音 VAD 及超过30秒拒绝。HTTPS 实际代理验证中文 WAV/WebM、日文 WAV/MP4、认证/Origin/格式/大小/损坏边界；Chromium 真实 MediaRecorder 使用公开语音假麦克风，识别后校对、草稿溢出保护、显式追加、取消及 pagehide 释放均通过，零聊天发送。原1账户/1会话/14消息保留，加密快照恢复到临时数据库验证通过。实际物理麦克风和 Safari 设备未验证，MP4 编码通过不能替代 Safari 真机验收。

最终 affected-tests：后端131、前端565；独立侧车15；类型、Ruff、Pyright、样式纪律、生产构建及三镜像构建通过。下载脚本重复校验真实权重通过；不匹配的已有文件拒绝覆盖。两份审查无阻塞项。TOL-283 已按用户决定停放 backlog。

```json
{"root_acceptance":"passed","runtime_version":"0.1.2","healthy_services":5,"backend_tests":131,"frontend_tests":565,"whisper_tests":15,"preserved_messages":14,"automatic_chat_sends":0,"manual_checks":["physical_microphone","safari_device"]}
```
