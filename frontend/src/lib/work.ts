/** Build-time work selection; keep the original work as the default for existing deployments. */
export const isProjectSekai = process.env.NEXT_PUBLIC_EIDOLON_WORK === "project-sekai";

export const PRIVATE_WORK = {
  name: "同行 · 教室的世界",
  description: "与教室的世界初音未来进行私人文字练习，可选本地录音转文字、点击朗读与经典 Miku 动态预览",
  label: "私人陪伴实验 · v0.1.3",
  title: "从一间教室，\n开始一段对话。",
  intro: "在教室的世界，与初音未来一起把想说的话慢慢说出来。你以同行者的身份参与，按照自己的节奏交流。",
  character: "初音未来",
  world: "教室的世界",
  format: "日语原文 · 中文字幕",
  enter: "登录，开始对话",
  instruction: "进入对话后，发送「开始练习」选择一幕。",
  practiceHint: "由 AI 引导，每次推进一小步。发送「结束练习」可随时回到普通交流。",
  practiceTitle: "三幕原创练习",
  practices: [
    { title: "第一声", text: "放学后的空教室，从一个词或一次轻敲节奏开始。" },
    { title: "不同的节拍", text: "聊聊与同伴不同的想法，练习把彼此的意见听完。" },
    { title: "留给明天的音符", text: "肯定今天的一件小事，自愿约定一个很小的下一步。" },
  ],
  scope: "这是非官方 AI 私人实验，三幕为原创文字练习，回复不代表官方设定。可选经典 Miku 旧版 Cubism2 样例动态预览，来自公开第三方镜像，仅在本部署私人试用；模型与 SDK 非开源资产，不是教室的世界服装。未配置或加载失败时回退静态预览。可用本部署 Whisper 将录音转成文字，校对后追加到草稿，不会自动发送；文字回复仍由外部语言模型生成。点击朗读只将所选回复文字交给本部署 Kokoro，支持日语和中文，不保存音频。本地合成音色，非官方角色声音；没有克隆初音未来的声音，不提供双向语音通话，不同步模型口型。",
  appearance: "默认使用文字头像，可选打开经典 Miku 旧版样例动态预览，未配置或加载失败时回退静态预览；不是教室的世界服装，没有可切换的外观，也不与朗读同步口型。",
} as const;
