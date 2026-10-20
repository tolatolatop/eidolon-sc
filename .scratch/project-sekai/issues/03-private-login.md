Type: task
Status: done

## 目标

首版私人体验不能依赖无需凭据的开发登录。增加可选的单人访问口令登录，未配置时原功能保持兼容；用户已授权从本机配置使用密钥和持续部署。

## 接口与实现范围

- `EIDOLON_PRIVATE_PASSWORD_HASH` → Settings.private_password_hash: str | None；格式固定 `scrypt-v1:<32个小写hex盐>:<64个小写hex摘要>`，scrypt N=16384,r=8,p=1,dklen=32；使用密码学随机16字节盐、constant-time比较。启动时校验格式，不打印内容。提供可复用 `hash_password` / `verify_password` 供部署生成使用，口令长度8～256，验证失败统一处理。
- 当哈希已配置，`GET /api/auth/providers` 增加 `private_login: true`（关闭时不增加，兼容原API断言）。`POST /api/auth/private-login` 接受 `{password: string}`，成功204，建立固定名字「同行者」账户会话；错误401「访问口令不正确」，不可选择他人名称，不打印口令。被封禁账户拒绝登录，不绕过原同意流程。关闭时路由不存在。
- 内存线程安全失败限流：单进程全局5次失败/60秒，超限429及 Retry-After；正确密码也需要遵守冷却，耗时scrypt只在限制允许后执行。测试使用可控时钟，不sleep。客户端地址不可信，不按可伪造header隔离。
- `EIDOLON_PRIVATE_ORIGIN` → Settings.private_origin: str | None，显式HTTP(S)站点origin（无路径/账号/查询/fragment）。只在private_password_hash存在时可配置。public_origin优先使用它；origin_allowed严格匹配它；会话cookie在HTTPS时Secure（现有domain行为保持）。允许localhost或者受保护的指定LAN入口。dev_login与private_password_hash同时配置拒绝启动。
- Engine 发给自定义身份角色的 CANNOT_SEND 静态提示把「制作人」换成user_role，避免首版当前回合身份矛盾，不改用户消息内容。补一项真实API提示词断言。
- 仅改 backend 和本票，主代理负责前端、部署与docs，不改锁文件。

## 验收与测试

- [x] 哈希/密码格式、错误、禁用、限流、固定账户、禁用开发登录组合、封禁、同意流程、Cookie、Origin 的针对性测试通过。
- [x] 密码不持久化明文、不进日志；已有登录与身份提示行为不变。
- [x] py_compile、Ruff、Pyright 与针对性pytest通过。

## Testing Decisions

使用现有 make_client / FakeLLM 和可控时钟验证API真实边界。不同线程要同锁检查与验证限流状态，避免并发绕过。原登录测试加回归验证。不要运行全量pytest、不要提交推送，不派审查子代理；主代理最终统一affected-tests和两份审查。基点97d4030b5a6a0ca704aad62b0b48ca6dfb4cdb2f。

## Comments

### 实现说明（票 03）

- 新增 `eidolon.private_login.hash_password(password)` / `verify_password(password, password_hash)`，固定 scrypt 参数与随机 16-byte 盐；密码长 8～256 字符，恒时比较摘要。Settings 启动时验证哈希，错误与 repr 不展示哈希内容。
- `POST /api/auth/private-login` 只在配置哈希时注册；所有错误/缺失/格式错误口令统一 401，不回显请求正文。scrypt 在工作线程执行，进程共享锁覆盖限流检查、验证及失败记录；失败五次后冷却，返回 429 与向上取整的 Retry-After，正确口令不能跳过冷却，成功不清空已有失败。
- 固定账户使用独立的 `private/owner` 登录身份，显示名「同行者」，不会接管同名 OAuth 或开发账户；沿用原会话、同意和封禁／删除规则（被封禁账户删除后身份仍封禁）。后端禁止解绑 private，前端需展示对应登录方式标签。
- PRIVATE_ORIGIN 优先于 DOMAIN，严格按完整 Origin 匹配，缺失 Origin 同样拒绝私人入口写请求；支持明确的 HTTP LAN origin，HTTPS 会话及 OAuth state Cookie 带 Secure。未启用私人配置时旧行为保持。
- 自定义身份角色的 CANNOT_SEND 静态提示仅替换服务端文字中的「制作人」，真实文字 API 回合断言已补充；用户消息保持原样。
- 检查：py_compile、修改文件 Ruff/Pyright、git diff --check 均通过。`uv run pytest -q tests/test_private_login.py tests/test_user_identity.py tests/test_sign_in.py tests/test_sessions.py tests/test_link_sign_in.py tests/test_hardening.py`：132 passed、2 个第三方弃用警告。
- 未改前端／docs／部署文件／锁文件，未提交推送；双份审查、affected-tests、真实模型与上线验收交主代理统一执行。

```json
{"ticket":"03","implementation":"complete","tests_passed":132,"checks":["py_compile","ruff","pyright","git diff --check"],"private_identity":{"provider":"private","subject":"owner","name":"同行者"},"pending":["code-review × 2","affected-tests","deployment acceptance"],"lockfile_changed":false}
```

### 双份审查后的修复

- 主代理汇总的后端 MAJOR：配置接受 `http://LOCALHOST:18739` 或 `https://private.example:443`，浏览器生成 Origin 时会小写主机名／去默认端口，导致严格匹配必然拒绝登录。
- 采用启动时拒绝非规范配置：主机名须小写，国际域名须 ASCII 格式，HTTP `:80`／HTTPS `:443` 须省略，IPv6 须用小写压缩格式，端口不得有前导零；短写或整数 IPv4 同样拒绝。保留请求严格匹配，并在配置错误中提示规范要求。
- 测试增加上述非规范输入及规范 IPv6、HTTP／HTTPS 非默认端口案例。`uv run pytest -q tests/test_private_login.py tests/test_sessions.py tests/test_sign_in.py`：102 passed、2 个第三方弃用警告；修改文件 py_compile、Ruff、Pyright 与 git diff --check 通过。
- 未执行全量测试，未提交推送。前端及部署问题由主代理修复并统一验收。
