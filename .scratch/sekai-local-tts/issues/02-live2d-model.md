Status: done

## 目标

TOL-278「用轻量级的TTS替代语音生成，然后模型也帮我加上。」root发出可选澄清后已说明按动态角色形象一并接入。仅现有miku-school，不增加角色。TTS票01先实现完再串行派本票；共享分支，不提交，root统一审查、验证、部署。基点26db0d68f8aaf270a599d26a9b07f5f001165b73。

root已将经典Miku旧版Cubism2样例下载到私人运行目录；文件不进Git或镜像。模型来源公开第三方镜像 Exrick/blog 固定revision64af2aa88b6313e269e99616d930f7ca07b61da8，路径live2d/assets/miku；SDK2 runtime来自pixi-live2d-display官方README链接的dylanNew/live2d，revisionfd9fd400845e9a00bb194fdac0b6635c753a1e8a，路径webgl/Live2D/lib/live2d.min.js。哈希清单在root工作区 `.delivery/miku-cubism2-model.json`，可读这个公开元数据但不要读运行目录的.env/用户对话。模型不是开源授权或教室世界服装，说明是经典Miku旧版样例，不声称官方当前moc3包已取得（当前官方端点403）。

## 验收

- [x] Settings可选 `EIDOLON_PRIVATE_LIVE2D_DIR`，管理员指定只读模型文件目录，默认未配置不影响旧应用。仅私人密码模式且UserId consent通过的API可访问。
- [x] 新模块的GET `/api/private-avatar` 返回available、固定同源model_url/script_url等最小信息，不回传主机路径；GET `/api/private-avatar/assets/{asset_path:path}` 仅明确允许固定已知文件名：miku.model.json、miku.moc、miku.physics.json、miku.2048/texture_00.png、motions/miku_m_01.mtn至06、motions/miku_shake_01.mtn、motions/miku_idle_01.mtn、live2d.min.js。拒绝遍历、绝对路径、未知文件/后缀、越界symlink；文件大小界限，nosniff和private no-store，无目录列表/远程代理/上传能力。模型JSON验证引用全部局部已知文件，绝不允许远程URL/声音加载。路由不基于用户目录参数。
- [x] 在已有形象预览Dialog按需加载Canvas显示真实Cubism2模型，经典Miku样例说明及来源准确；默认有idle/眨眼和指针跟随，可选一个显式「播放动作」按钮，不要音频自动播放。只在打开预览时加载模型并创建renderer；关闭、切换、取消/晚到结果销毁模型、ticker、texture、WebGL；ResizeObserver跟随容器，移动和横屏有界，prefers-reduced-motion/页面隐藏暂停或静态 fallback。未配置、加载失败、无WebGL时回退原静态预览，并准确提示，不能无限loading。
- [x] 使用pixi.js==6.5.10、pixi-live2d-display==0.4.0 cubism2-only动态导入，SDK script先从同源认证API加载，注册ticker。对CSP使用@pixi/unsafe-eval==6.5.10的静态polyfill（查官方用法install），不要添加unsafe-eval或放宽跨域/远程脚本。没有外部CDN访问；script loader共享promise避免并发，超时/失败可重试。依赖锁定，Next本地guide先读。不要复制SDK/model二进制到repo。
- [x] work.ts/i18n/privacy/terms的原静态only说明与TTS票01最终文案协调为可选经典Miku动态预览，非学校服装，非模型开源和官方音色，不新增角色、不承诺声音口型同步。必要单测验证私有认证、未配置、文件/引用/遍历/symlink边界；前端逻辑定向测试而非镜像组件测试。

## Testing Decisions

读AGENTS.md、docs/agents/implementing.md、frontend/AGENTS.md、Next相关本地文档；用python-coding-guidelines/typescript技能。只跑定向pytest、typecheck、必要逻辑vitest、discipline、Ruff/py_compile。不跑affected-tests/next build/Playwright/字体，root统一完成。不提交推送，不动Compose及运行服务，不读密钥/用户文本，不改原游戏。

## 资料

https://github.com/guansss/pixi-live2d-display （Cubism2/PIXI6、registerTicker、runtime来源）
https://api.pixijs.io/%40pixi/unsafe-eval.html （静态CSP polyfill，不开启unsafe-eval）

## Comments

root已准备本地样例文件和哈希，后端会挂载 /characters/live2d/miku 并设置对应环境变量。模型及SDK只用于本地私人试用，不打包进开源源码或镜像。

### 实现说明（票 02）

代码实现与定向验证已完成，等待 root 串行构建、Playwright 真模型验收及整体验证后关票。未提交、推送或部署，未修改 Compose、下载脚本和 TTS 核心。

- 后端新增 private_avatar_api.py，Settings 增加 EIDOLON_PRIVATE_LIVE2D_DIR。接口复用 UserId 的登录/consent 验证并限私人密码部署；仅固定资源白名单，逐级 no-follow 文件打开、大小界限、严格模型引用 schema、private no-store 和 nosniff。所有文件由管理员只读目录提供，仓库无 SDK/model 二进制。
- 前端新增 PrivateAvatarPreview、privateAvatar 和 privateAvatarRenderer。打开 Dialog 后才加载；固定同源 SDK 共享 promise 与重试；Cubism2-only 动态导入；PIXI ShaderSystem 静态 install；自己的 ticker/texture/renderer/context 在关闭和失败时释放，晚到结果清理；纹理查询串隔离旧加载和新预览的全局缓存所有权。ResizeObserver、页面隐藏暂停、减少动态效果静态回退与20秒加载截止。
- 经典 Miku 旧版第三方镜像/非学校服装/模型及 SDK 非开源/无朗读口型同步文案已更新，与票01本地 Kokoro 文案共存。
- 定向 pytest：tests/test_private_avatar_api.py 28通过；Vitest：privateAvatar、privateAvatarRenderer、work、contentSecurityPolicy 共18通过；npm run typecheck、shadcn纪律、Ruff、py_compile、git diff --check 通过。
- 依赖准确锁定 pixi.js 6.5.10、pixi-live2d-display 0.4.0、@pixi/unsafe-eval 6.5.10。插件误列生产依赖的发布CLI gh-pages用局部override升6.3.0，消除新增Critical。现审计仍有high，来自既有braces/fast-glob链及发布工具链传播；浏览器Cubism2 bundle未导入gh-pages。所有既有锁文件package版本均未变化。
- root接续：重生落地页字体；生产build/真实Cubism2渲染（含眨眼/idle/动作/指针）、桌面/手机/横屏、关闭重开/加载中关闭/无WebGL/减少动态效果/隐藏页面与CSP网络零外部请求检查；完成两份整体验证后逐项勾验收。

官方用法依据：https://github.com/guansss/pixi-live2d-display （Cubism2-only、registerTicker）；https://github.com/pixijs/pixijs/blob/v6.5.10/packages/unsafe-eval/README.md （install({ ShaderSystem })）。

### root 独立审查与修复

两份补审均无Critical/Major。后端Minor：管理员root的祖先目录属可信部署边界，已收窄no-follow注释；相对资产目录逐层no-follow保持。安装脚本已改先fstat普通文件与精确长度、有限流式hash，拒绝symlink组件，与API规则一致；实际文件重复校验及错误size/symlink回归通过。

前端Minor：纹理加载Promise可能在dispose后永不settle，不能把内部模型清理托付给setup结束。root增加显式取消收束、modelLoaded迟到清理，并在内部模型已存在时立即调用真正destroy（包括motionManager/XHR）；保持每次预览独立纹理缓存键。新增「内部模型已有、纹理Promise永不完成」回归，5项renderer测试及typecheck通过。

最终集成affected-tests：后端177、前端580通过；生产Next构建通过。真实浏览器验收由root继续，未把单测写成已经上线。

### root 生产交付

v0.1.3 已在原HTTPS地址上线，六容器健康，原1账户/1会话/14消息保留。真实断网Kokoro生成中日公开句，Whisper回转与原文忽略标点后相符。HTTPS真实消息朗读成功、CPU4线程且无外网端口；浏览器验证真实WAV播放/停止、显式健康重试、真实Miku模型渲染/动作、关闭释放WebGL、移动端/减少动态效果/故障静态回退。测试没有发送聊天消息，没有外部浏览器资源请求。原生推理取消限制、Safari和物理麦克风真机仍按文档保留为人工体验项。最终本地177后端/580前端/38TTS服务测试、类型与纪律、生产构建通过；快照恢复到临时库验证通过。root接续提交推送及PR交付。
