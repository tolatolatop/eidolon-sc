# 私人陪伴版本

范围：日服公开简介、教室的世界初音未来、同行者身份和三幕原创音乐练习。一次部署只有一个私人同行者账户；访问口令持有人共享该账户。未导入正式剧情，没有启用礼物、好感度、跨世界记忆或旧同步任务。v0.1.1 增加本地 HTTPS、可选静态形象预览与火山语音朗读接口；语音必须配置服务和音色后才能使用。后续可以替换角色包与构建时作品配置，再迁移到自研角色。

## 构建

在仓库根目录执行后端构建：

```sh
docker build -t sekai-companion-backend:0.1.1 backend
```

私人前端可以用标准 Docker 构建的 `--build-arg NEXT_PUBLIC_EIDOLON_WORK=project-sekai`。也可以先在主机安装锁定依赖、检查生产构建，再打包 standalone 产物，避免重复下载依赖：

```sh
cd frontend
npm ci
NEXT_PUBLIC_EIDOLON_WORK=project-sekai npm run build
cd ..
docker build -f frontend/Dockerfile.private -t sekai-companion-frontend:0.1.1 frontend
```

两种方式都排除旧角色海报、礼物与重置卡插画。不开作品开关时，标准 Dockerfile 保留原应用。不要把 `Dockerfile.private` 用于没有设置作品开关的构建产物。

## 运行配置

使用独立主机目录，首个部署为 `~/services/sekai-companion/`。它保存 `compose.yml`、`compose.env`、私有 `.env`、`backup.env`、`.access-password`、独立 `characters/`、`private_backup.py` 和 `backups/`。主机目录权限为 700，密钥、口令与环境文件权限为 600；它们不进 Git 或 issue 附件。

- `.env`：`CHAT_LLM_PROTOCOL=chat-completions`、对话模型地址、密钥、模型、限额，以及 `EIDOLON_PRIVATE_PASSWORD_HASH`、`EIDOLON_PRIVATE_ORIGIN`、`EIDOLON_SECRET_KEY`。首版使用 OpenRouter 的 `anthropic/claude-sonnet-4.6`，请求中禁用思考输出并选择不收集数据的提供方路由；具体服务条款仍以提供方为准。
- `EIDOLON_PRIVATE_PASSWORD_HASH` 是 `eidolon.private_login.hash_password()` 生成的 scrypt 摘要，不能填写明文。默认格式固定，启动时验证。`EIDOLON_DEV_LOGIN` 必须关闭，错误口令有全进程冷却限制。
- `EIDOLON_PRIVATE_ORIGIN` 必须是浏览器的规范 origin，包括协议及非默认端口，没有结尾斜杠。比如 `http://192.168.1.112:18739`；大写主机名或显式默认端口会被拒绝。通过 HTTPS 域名访问时改为对应 HTTPS origin，Cookie 随之使用 Secure。
- `backup.env` 只保存 `SEKAI_BACKUP_KEY`，其格式为 Fernet 的 URL-safe Base64 32 字节密钥。数据库先用 SQLite 一致性备份，再认证加密，每日一份，保留 14 天。备份密钥丢失后无法解密；主机目录和数据库都丢失时，这份同机备份不能用于灾难恢复。
- `compose.env` 指明 `SEKAI_ENV_FILE`、`SEKAI_CHARACTERS_DIR`、`SEKAI_BACKUP_ENV_FILE`、`SEKAI_BACKUP_DIR`、`SEKAI_BACKUP_SCRIPT` 的绝对位置，另设 `SEKAI_BIND_IP` 和 `SEKAI_PORT`。默认端口 18739，不占用原应用端口；数据库卷名为 `sekai-companion-data`。
- HTTPS 网关另需 `SEKAI_TLS_HOST`（证书中的局域网 IP）、`SEKAI_HTTPS_PORT`（默认 18740）、`SEKAI_TLS_DIR`（证书目录）和 `SEKAI_NGINX_TEMPLATE`（本目录模板的私有运行副本）。`SEKAI_GATEWAY_IMAGE` 可锁定经核验的 nginx 镜像 digest。前端不直接发布端口，18739 仅跳转到 HTTPS。
- Compose 使用独立的 `10.211.39.0/24` 网络，避免耗尽 Docker Desktop 的自动地址池；在其他主机有冲突时，通过 `SEKAI_SUBNET` 指定经核对的空闲网段，不删除或改动已有应用网络。

口令只能在部署主机查看 `.access-password`，不要贴进 issue、聊天或日志。API 密钥从用户授权的本机环境获取，不随镜像构建，也不交给浏览器。首次登录后仍需同意隐私说明；删除账户后重新登录会建立新账户。

## 本地 HTTPS

在首次启动新版 Compose 前，生成私有本地 CA 和带 IP SAN 的服务器证书。脚本需要 Python 3 和 OpenSSL；拒绝覆盖已存在的证书或私钥。IP 更换后，在新的空目录签发并切换配置。

```sh
sh deploy/sekai/generate-tls.sh 192.168.1.112 "$HOME/services/sekai-companion/tls"
```

只有 `server.crt` 和 `server.key` 挂载给网关；根 CA 私钥不进入容器。把 **`root-ca.crt` 公钥证书**复制到实际使用的客户端，核对以下命令的 SHA-256 指纹后导入受信任根证书。Windows 导入「受信任的根证书颁发机构」，macOS 在钥匙串设置信任，iOS 安装描述文件后还需在「证书信任设置」启用；Firefox 可能需要在自身证书设置中导入。测试结束可撤销这份本地 CA 的信任。不要分发任何 `.key` 文件。

```sh
openssl x509 -in "$HOME/services/sekai-companion/tls/root-ca.crt" -noout -fingerprint -sha256
curl --cacert "$HOME/services/sekai-companion/tls/root-ca.crt" https://192.168.1.112:18740/api/health
```

`.env` 中设置 `EIDOLON_PRIVATE_ORIGIN=https://192.168.1.112:18740`；地址必须与实际入口完全一致。Cookie 将变为 Secure，旧的 HTTP 页面跳转过去后需重新登录。自签证书不自动获得浏览器信任：仅点击忽略证书警告不保证麦克风可用，需完成客户端信任。HTTPS 只准备了浏览器能力，完整双向通话仍需语音识别等服务。

## 静态形象与朗读

私人对话页在角色配置包含 `background` 时展示「形象预览」。本机使用 [Live2D 官方 Miku 免费样例](https://www.live2d.com/en/learn/sample/hatsune-miku/)页面的静态展示图，来源与 SHA-256 记录见 `examples/project-sekai/assets.json`。这是经典 Miku 外观，不是教室的世界服装。第三方图片和模型只存放在私有角色目录，不随代码或镜像分发；未安装 Live2D 动态渲染器。免费分发样例不等于开源模型。

可将该公开展示图下载到私有角色目录的 `images/miku-live2d-preview.jpg`，再添加：

```toml
background = "images/miku-live2d-preview.jpg"
```

完整模型候选包含 `.moc3`、`.motion3.json`、物理及模型配置；当前下载端返回 403，未把候选模型冒充已安装模型。

火山配置及朗读限制见 [语音朗读说明](../../docs/sekai-read-aloud.md)。未配置密钥、音色时界面准确显示待配置；没有自动复刻音色，没有恢复完整电话入口。

## 启动、日志与停止

在运行目录操作：

```sh
cd ~/services/sekai-companion
docker compose --env-file compose.env -f compose.yml up -d --wait --wait-timeout 90
docker compose --env-file compose.env -f compose.yml ps
docker compose --env-file compose.env -f compose.yml logs --tail 60
```

Docker 的 `unless-stopped` 管理服务生命周期，任务结束后无需 agent 维持进程。后端和前端都不直接发布主机端口；浏览器只访问 HTTPS 网关。旧局域网 HTTP 入口仅重定向，本次没有开放公网域名。

```sh
docker compose --env-file compose.env -f compose.yml stop
# 下次恢复
docker compose --env-file compose.env -f compose.yml up -d --wait --wait-timeout 90
```

停止保留数据库和加密备份。不要运行 `down -v`，它会删除数据库卷。服务容器及镜像名称均以 sekai-companion 开头，不依赖工作任务的子进程。

## 快照、验证与回滚

手动增加一份快照：

```sh
docker compose --env-file compose.env -f compose.yml exec -T backup python /ops/private_backup.py snapshot
```

从日志取得快照文件名，用下列命令验证解密和 SQLite 完整性；它在临时目录中恢复，不修改线上数据库：

```sh
docker compose --env-file compose.env -f compose.yml exec -T backup python /ops/private_backup.py verify /backups/实际快照文件名.db.fernet
```

`restore <archive> --output <new-file>` 只写新文件，拒绝覆盖已存在的数据库。正式数据回滚前先停止前后端、另做快照，再把已验证的恢复文件交给部署者确认后替换；首版部署未覆盖任何原应用数据库。

代码回滚使用旧的本地镜像标签或保留的 image ID，修改 `compose.env` 的 `SEKAI_FRONTEND_IMAGE` / `SEKAI_BACKEND_IMAGE` 后重新 `up -d`，数据库卷保持原样。本次新增登录身份不改原有表结构。源码入口在应用导航的 GitHub 链接中，许可证沿用 AGPL-3.0-or-later；角色与第三方素材权利另计。
