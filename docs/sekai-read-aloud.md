# 私人版点击朗读

私人版对话可手动朗读已经完整保存的回复。采用火山引擎 V3 HTTP Chunked 语音合成，不需要 STT，不开启实时语音通话。普通作品模式保持原状。

在部署的私有环境文件中配置以下值，并通过容器环境传入后端。不要使用 `NEXT_PUBLIC_` 前缀，不要提交密钥。

```dotenv
VOLCENGINE_TTS_API_KEY=
VOLCENGINE_TTS_SPEAKER=
VOLCENGINE_TTS_RESOURCE_ID=seed-tts-2.0
```

前两项留空时界面显示「朗读待配置」，不会为每条消息请求合成。`SPEAKER` 必须是账户已授权、与资源版本匹配、支持日语的音色 ID。服务端优先朗读保存的日语原文并移除控制标记，指定 `explicit_language=ja`；没有日语原文而回退到 `text` 字段时，本产品将其按中文处理，指定 `explicit_language=zh-cn`。语言设置通过 `req_params.additions` JSON 字符串发送，所选音色需支持对应语种。不接收浏览器提交的朗读文字。密钥仅保存在服务器环境中，不返回浏览器，也不进入原有 Fish Audio 的计价和服务健康检测。

普通预置音色不是 Miku 官方角色音色。声音复刻需要另行取得授权、开通声音复刻资源并训练音色，使用相应 `seed-icl-*` 资源与复刻 speaker ID；不能仅修改角色名称获得角色音色。没有真实密钥和已授权音色时只能验证协议、权限和界面，无法确认实际发音、音色质量或付费调用成功。

每位用户同时只能合成一条，结束、失败或取消后冷却三秒。单条上限为 2000 字符且 UTF-8 不超过 6000 字节；整体请求最多 35 秒，响应最多 12 MiB，解码后音频最多 8 MiB。只把音频暂存于请求和浏览器内存，不写入数据库，不允许共享缓存。点击停止、换消息、切换对话或离开页面会取消请求并回收音频对象 URL；上游已接受的合成仍可能产生费用。当前限流保存在单个后端进程内，私人版使用一个 worker；多 worker 部署前须改用共享限流。

若 Safari 等浏览器要求新的播放手势，已生成的音频会留在当前页面内存，按钮显示「播放朗读」；再次点击直接播放同一份音频，不重复请求收费合成。点击取消、切换回复或离开页面仍会回收。私人版 CSP 单独允许 `blob:` 音频，普通作品模式的媒体策略不变。

API 需要有效会话、同站 Origin、隐私政策和条款同意；只允许访问自己的对话中已经保存的角色回复。私人密码登录未开启时此功能返回 404。`GET /api/read-aloud` 仅返回是否已配置，`POST /api/conversations/{conversation_id}/messages/{message_id}/read-aloud` 返回 MP3；它不保存新音频或新消息。

协议依据：[火山引擎官方 HTTP Chunked/SSE 单向流式 V3 文档](https://docs.volcengine.com/docs/DoubaoVoice/HTTPChunkedSSEUnidirectionalStreaming-V3?lang=zh)。实现调用 `/api/v3/tts/unidirectional`，使用 `X-Api-Key`、`X-Api-Resource-Id`、`X-Api-Request-Id`，按行读取 JSON 并拼接 base64 音频，必须收到 `20000000` 终止码后才返回音频。

若部署者配置了角色 `background` 预览图片，私人页首提供「形象预览」入口，完整显示静态图片并链接 [Live2D 官方 Miku 样例页](https://www.live2d.com/en/learn/sample/hatsune-miku/)。这是经典 Miku 免费样例预览；教室的世界服装待适配，动态模型尚未接入。
