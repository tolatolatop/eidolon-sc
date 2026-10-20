离线 Kokoro v1.0 int8 朗读侧车；独立 Python 3.11 锁文件，无 torch、CUDA 或 GPU 依赖。仅将服务接到私人后端内网，不公开端口。运行一个 ASGI worker，以 UID 10001、只读根文件系统和只读 `/models` 挂载运行；提供有大小限制的 `/tmp` tmpfs（jieba 缓存），不要保存请求体、音素或音频，不启用访问日志。

日语使用官方 `misaki.cutlet.Cutlet()` 的 Kokoro v1.0 前端，锁定 fugashi 1.5.2、unidic-lite 1.0.8、jaconv 0.5.0 和 mojimoji 0.0.13。精简日语词典随 unidic-lite 在镜像中预装，启动检查本地的 sys.dic/unk.dic/matrix.bin/char.bin/dicrc/mecabrc；没有任何启动下载步骤。不安装完整 Unidic、pyopenjtalk、misaki[ja] 或英语 torch/spaCy 依赖。中文使用 `misaki.zh.ZHG2P()` 的 v1.0 路径。

只读模型挂载必须包含 `/models/kokoro-v1.0.int8.onnx`、`/models/voices-v1.0.bin`。缺少模型或镜像内词典文件直接启动失败。容器启动预热使用固定公开的「こんにちは。」「你好。」；正式启动可完全断网。权重与软件许可证、下载及完整性校验由部署者维护。

- `GET /health`：预热完成返回 `{"ready":true}`，否则 503。
- `POST /synthesize`：`Content-Type: application/json`，严格字段 `{"text":"你好。","language":"zh-cn"}`，语言只接受 `ja` 与 `zh-cn`，固定音色分别 `jf_alpha` 与 `zf_xiaobei`。
- 请求流最多 4096 字节、15 秒；文字最多 300 Unicode 字符、1200 UTF-8 字节；拒绝空串、非法 UTF-8、控制字符及额外字段。
- 完整的有界回复先做一次 G2P，保持「今日」等跨边界词语完整；空音素或模型词表未覆盖的符号安全返回 422，预热也执行同样的完整词表检查。总音素至多 2400；每次 ONNX 输入至多 400 音素、至多 12 段；音频总量最多 60 秒。90 秒预算在分段之间检查，HTTP 最多等 95 秒。原生 ONNX 的单次调用无法强制中断或提前限制其内部内存分配，取消、断线或超时后，该调用可能继续，实际工作线程持锁到结束，新请求返回 429，不进入无界队列。若原生调用挂起，请由部署者安全重启单个 TTS 容器（先停止接收新请求）；不得通过释放锁再派任务恢复。
- 输出为内存生成的 24kHz、单声道 PCM16 WAV；拒绝空、非有限数值、采样率错误或超限输出。所有响应 `Cache-Control: no-store`，异常响应不回显文字、路径或模型错误。

Kokoro 是通用合成音色，非官方角色声音，没有克隆初音未来声纹。Whisper 录音识别和本服务的点击朗读均在本部署处理；聊天 LLM 仍由既有外部服务处理。

定向测试：`uv run --project deploy/sekai/tts pytest deploy/sekai/tts/tests`。服务边界测试使用 mock；真实 G2P 回归仅使用已安装的包内词典和 Kokoro DEFAULT_VOCAB，不加载 ONNX 权重，不在测试过程中下载词典。
