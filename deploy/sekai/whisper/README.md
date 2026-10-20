本地 Whisper 录音输入侧车，与角色语音合成无关。使用 multilingual small、CPU int8、4线程，无 CUDA / torch 依赖，不使用 GPU。源码接口依据 [faster-whisper](https://github.com/SYSTRAN/faster-whisper) 与 [PyAV](https://pyav.org/docs/stable/api/audio.html)。

模型由部署者预先下载到独立目录，完整 small 权重只读挂载到 `/models/small`，不进入 Git 或镜像。`WHISPER_MODEL_PATH` 可指定其他本地目录；加载使用 `local_files_only=True`，镜像同时开启 Hugging Face offline 模式，VAD 随 faster-whisper 包提供。启动缺模型即失败。必须只运行一个 Uvicorn worker，并用 Docker 内部网络隔离侧车、禁止公网端口与外网出口。

主后端设置 `EIDOLON_LOCAL_WHISPER_URL=http://whisper:8000`，部署关闭朗读用 `EIDOLON_READ_ALOUD_ENABLED=0`（默认 `1` 保持旧部署兼容）。侧车不需要密钥。主后端只开放已登录且同意条款的私人账户代理，仍检查 Origin。`GET /api/voice-input` 返回服务可用性，`POST /api/voice-input/transcribe?language=auto|zh|ja` 接受原始音频字节。

侧车接口 `GET /health` 在模型加载完成后返回 `{"ready":true}`；`POST /transcribe?language=auto|zh|ja` 接受音频原始字节（浏览器 webm、mp4，另支持 wav、ogg、mp3、flac），返回 `{"text":"识别文字","language":"zh"}`。每段最多5MiB和30秒，单段一个音轨，解码后16kHz单声道。PyAV 逐帧解码并检查采样数，推理与解码离开 ASGI 事件循环。一个全局锁拒绝并发，不建立无界队列；客户端取消或代理超时不能提前释放仍在运行的推理锁。解码另有逐帧10秒时限（原生解码调用由容器资源上限兜底）。静音通过 VAD 返回空文字；错误不回传录音或模型路径。

录音仅在内存中处理，不保存到磁盘，不记录音频或识别文字。识别结果须由用户校对并显式追加到草稿，原有草稿保留，绝不自动发送。点击发送后的文字仍交给既有外部语言模型；本部署并非所有聊天离线。取消、离页或切换对话释放麦克风并忽略迟到结果。

录音时请保持页面在前台。前端使用单调时钟计时并提前留出编码余量，系统时钟回拨不会延长录音；浏览器挂起、后台限速或设备休眠仍可能延迟停止事件，前端不保证跨挂起的绝对时限，服务器始终拒绝解码后超过30秒的音频。线程内的原生解码与推理无法被 HTTP 超时或取消强制中断；若侧车持续卡住，在部署 Compose 目录执行 `docker compose --env-file compose.env -f compose.yml restart whisper` 重启该服务，保留模型挂载与所有数据卷，勿使用 `down -v` 或删除卷。

开发定向验证：`uv sync`，`uv run pytest`。运行服务：`uv run uvicorn server:app --host 0.0.0.0 --port 8000 --workers 1 --no-access-log`。生产使用外层 Compose 的4CPU、4GiB、只读根目录和内部网络限制；不得把此无认证侧车直接对外暴露。
