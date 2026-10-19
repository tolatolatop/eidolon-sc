# eidolon-sc →《初音未来：缤纷舞台》迁移研究

核对日期：2026-10-19。任务 TOL-278；源码基点：`tolatolatop/eidolon-sc@4f55fb03918dd0d59290181a8077c513f3bad488`。本次交付是单角色文字原型及可执行路线，尚非全作品改版。目标游戏的区服、版本、剧透上限和安装平台未指定；暂按日服官网公开简介、独立本机 Web 应用验证。它不安装进游戏，也不连接游戏账号或服务器。

## 结论与已有实现

eidolon-sc 是可复用的角色陪伴应用，有完整的登录、文字/语音回合、检索、用户记忆、好感度与运维能力。但它的领域模型和资源管线紧贴《偶像大师 闪耀色彩》，不能通过换名字完成迁移。

本次保留原作配置，新增 `examples/project-sekai/`：只加载 `miku-school`。选择教室的世界这一形态；背景是自行转述的公开简介，三幕音乐练习是新写的同人提纲。简短内容直接放入人设，所以无需向量模型、判断模型或官方剧情文件就能进入对话提示词。`facts/` 保留出处，供后续检索准备。

后端新增成对的 `user_role` / `user_identity` 可选字段，接入当前身份和时间、生日提示词，避免把同行者强设为 283 制作人及默认男性。旧角色不配这两项时维持原行为。语音、照片、立绘、礼物和检索未纳入本轮体验验证；没有添加媒体素材。

## 仓库结构与迁移差距

| 能力 | 现有位置 | 能复用的部分 | 改造要求 |
|---|---|---|---|
| 角色与资料 | `characters/`、`backend/src/eidolon/characters.py` | TOML 加载、人设全文、资料按节解析 | 独立作品包；角色身份不能只有显示名 |
| 文字/语音回合 | `engine.py`、`assembly.py`、`reply_format.py` | 流式回复、日语和中文字幕、工具调用 | 本轮仅接文字；剩余工具、送礼叙述等仍有制作人术语 |
| 用户档案 | `producer.py`、`store/` | 称呼、性别、生日、时区 | 本轮扩展身份提示；前端仍叫制作人档案 |
| 世界设定 | `world.py`、`world_sync.py` | 数据文件加载、出处记录 | 固定事务所、每人一个组合；不能准确表达多世界初音。本轮不使用旧 `world.json` |
| 剧情导入 | `story_import.py`、`story_sync.py`、`mirror.py` | Episode/Line、出场者过滤、按需回忆 | 旧 CSV/JSON、脚本编号、失败路线、镜像源均为 SC 专用，不能直接导入 SEKAI JSON |
| 用户记忆 | `memory.py`、`retrieval.py` | 用户隔离、来源角色、可删除 | 同一用户跨角色共享；需作品与世界作用域，防止不同世界串记忆 |
| 视觉与音色 | `stand_fetch.py`、`stand_outfits.py`、前端 Spine 3.6 | 通话组件与无图降级 | SC 的 idolId/enzaId 不是 SEKAI 角色 ID；Live2D 等格式需另行验证与授权 |
| 门面与法律说明 | `frontend/src/app/`、`frontend/src/i18n/` | 登录、对话 UI | 28 色落地页、组合搜索、品牌、条款、静态插画都要处理；本轮未替换 |
| 运行与备份 | `config.py`、`docker-compose*.yml`、`deploy/` | 后端服务、持久化、备份 | 单独数据库和挂载目录，停用旧同步定时任务；不可覆盖用户现有数据 |

## 角色和剧情设计

官方区分各个世界中的初音，其形象和支持对象随世界变化。不能把现实虚拟歌手、教室、舞台、街头、奇幻和空无一人的世界中的初音经历无条件合并。[虚拟歌手介绍](https://pjsekai.sega.jp/character/virtualsinger/index.html)

官网将世界与人的心意联系起来；教室的世界与 Leo/need 相关，初音和流歌承担支持与倾听的角色。这足以支撑一个有限的陪伴原型，不能据此推导具体活动经历。[故事简介](https://pjsekai.sega.jp/story/index.html) · [Leo/need](https://pjsekai.sega.jp/character/unite01/index.html)

下一步用组合与世界作为内容分区：Leo/need、MORE MORE JUMP!、Vivid BAD SQUAD、Wonderlands×Showtime、25点，Nightcord见，以及虚拟歌手。各区保留独立的初音形态；首轮只扩展 Leo/need，待人物关系和剧透控制验收后再拓展其余组合。组合现状应逐页核对，不能把本轮公开简介当作完整的六周年剧情资料库。

建议的后续标准化剧情模型（设计，未实现）：

```json
{
  "work_id": "project-sekai",
  "edition": "jp",
  "timeline_cutoff": "待用户指定",
  "unit_id": "leo-need",
  "sekai_id": "school",
  "character_variant_id": "miku-school",
  "episode_id": "fan-original:first-note:01",
  "canon_status": "fan_original",
  "cast": ["miku-school"],
  "source_url": null,
  "rights_status": "original_outline",
  "spoiler_level": "intro_only"
}
```

`episode_id` 保留来源与稳定标识，不能用标题或同名说话人猜世界。只有说话人标记「ミク」不足以决定是哪位初音，必须结合来源世界、区服和剧情上下文。原作设定、同人场景与用户聊天记忆分层，用户的练习进度不能回写为官方剧情事实。

## 许可证与素材边界

源码的 `LICENSE` 和 `backend/pyproject.toml` 标为 AGPL-3.0-or-later。修改后的网络服务需要考虑 AGPL 第 13 条向交互用户提供对应源码的义务；代码许可不授予角色、剧情、美术、音乐、声优声音或第三方 runtime 的权利。仓库中的既有 SC 素材策略也不能直接视为本改版的授权。[源码许可证](https://github.com/tolatolatop/eidolon-sc/blob/main/LICENSE)

SEKAI 官方二创规则包含适用主体、非营利条件和禁止使用官方插画数据等约束；不能推断“非营利 AI 服务已自动获准”。Piapro 角色另有优先适用的角色指南，商业、宣传等用途需单独审查。本报告是项目范围判断和待办依据，不是法律授权结论。[SEKAI 二创指南](https://pjsekai.sega.jp/guideline/index.html) · [Piapro 角色指南](https://piapro.jp/license/character_guideline) · [PCL 摘要与正文入口](https://piapro.jp/license/pcl/summary)

本轮没有抓取完整游戏剧情、提取安装包、复制官方图片、下载音源或克隆音色。公开发布和收费前，由用户确认发行主体、地区、用途以及授权；如果需要完整剧情、图像或语音，再提供可用来源和使用范围。未经确认，不自动开启公开服务或相关资源抓取。

## 路线与里程碑

| 阶段 | 可执行工作 | 验收条件 |
|---|---|---|
| M0：本轮 | 单角色配置、身份适配、三幕原创提纲、离线 API 测试 | 原包可加载；文字回合用初音场景和同行者身份；旧配置兼容 |
| M1：人工体验 | 确定区服、世界、用户关系、剧透点；配置真实 LLM | 人工逐条通过示例 README 的验收问题；记录模型、提示词版本和出戏案例 |
| M2：剧情资料 | 基于获准来源实现独立适配器、出处与剧透过滤、版本标识 | 正式剧情与同人场景分开；同名初音映射准确；越界情节不检索 |
| M3：组合体验 | 完成 Leo/need 关系资料、世界作用域和群组导航 | 角色只回忆可见剧情；跨世界、跨用户无记忆污染；再扩其他组合 |
| M4：发布 | 替换门面、文案与条款，审查所有资产与音色许可，打包与回滚 | 授权与源码义务确认；无旧品牌遗漏；备份恢复演练和用户删除测试通过 |

本轮与 GLOSSARY 的「单作品」「同一人物无多版本」以及 ADR-0003 的旧素材策略存在有意的方向差异：原系统仍维持原定义，本轮只用隔离包验证，不悄悄改写全部领域模型。M2/M3 前应为作品、世界与角色形态重新记录 ADR。

## 验证与限制

自动化测试验证真实角色包、启动前校验、API 创建对话和流式双语回复，以及提交给假模型的提示词。假模型不验证内容质量、遵循提纲的可靠性或长期剧情一致性。没有真实付费 LLM、浏览器视觉、语音和移动端验收；不能声称已完成这些检查。

配置和启动步骤见 [单角色示例](../../examples/project-sekai/README.md)。原 `characters/` 和现有数据库均不改动；停止原型进程并切回原配置即可回滚。正式迁移时必须另做备份与数据隔离方案。
