/** Build-time work selection; keep the original work as the default for existing deployments. */
export const isProjectSekai = process.env.NEXT_PUBLIC_EIDOLON_WORK === "project-sekai";

export const PRIVATE_WORK = {
  name: "同行 · 教室的世界",
  description: "与教室的世界初音未来进行私人文字练习",
  label: "私人文字实验 · v0.1",
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
  scope: "这是非官方 AI 角色实验，仅供私人体验。对话可能出错，不代表官方设定；三幕内容为原创练习，不含正式剧情、官方插画、立绘或角色音色。首版只开放文字对话。",
  appearance: "本次实验使用文字头像，没有可切换的外观。",
} as const;
