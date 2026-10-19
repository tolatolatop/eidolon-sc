import { PRIVATE_WORK } from "@/lib/work";

import { zh } from "./zh";

/** Preserve the shared copy structure (including function signatures), changing only terminology. */
function companionTerms<T>(node: T): T {
  if (typeof node === "string") return node.replaceAll("制作人", "同行者").replaceAll("Eidolon-SC", PRIVATE_WORK.name) as T;
  if (typeof node === "function") {
    const original = node as (...args: unknown[]) => unknown;
    return ((...args: unknown[]) => companionTerms(original(...args))) as T;
  }
  if (Array.isArray(node)) return node.map(companionTerms) as T;
  if (node && typeof node === "object") {
    return Object.fromEntries(Object.entries(node).map(([key, value]) => [key, companionTerms(value)])) as T;
  }
  return node;
}

const base = companionTerms(zh);

export const projectSekai: typeof zh = {
  ...base,
  app: { ...base.app, name: PRIVATE_WORK.name, description: PRIVATE_WORK.description },
  share: { title: PRIVATE_WORK.name, description: PRIVATE_WORK.scope },
  legal: { ...base.legal, disclaimer: "非官方 AI 私人陪伴实验，与版权方无关。" },
  conversationList: { ...base.conversationList, noneSelected: "选择初音未来开始对话", search: "搜索角色", noMatch: "没有找到这位角色" },
  login: { ...base.login, lede: PRIVATE_WORK.intro + PRIVATE_WORK.scope, castTitle: "本次可以对话的角色" },
  consent: { ...base.consent, intro: "文字对话与档案会保存在这台服务器上，并交给部署者配置的语言模型处理。配置朗读后，只有点击朗读时，所选回复才会发送给火山引擎合成语音；本部署不保存音频，不上传麦克风声音，也不开启双向语音通话。可选形象为官方免费样例的静态预览。详情请看{privacy}和{terms}。" },
  privacy: {
    ...base.privacy,
    sections: [
      {
        title: "本次私人实验保存什么",
        items: [
          { term: "私人登录", text: "服务器只保存访问口令的加盐摘要、固定同行者身份和登录会话，不保存你输入的明文口令。口令不交给语言模型。" },
          { term: "文字对话与档案", text: "你输入的文字、角色回复、对话标题及你填写的称呼、性别、时区和生日保存在本部署的独立数据库中。本版没有正式剧情库，也未启用照片、好感度、礼物或跨世界长期记忆。" },
          { term: "点击朗读", text: "配置后，只有点击朗读时，所选角色回复才会发送给火山引擎合成语音。音频仅暂存在请求与浏览器内存中，本部署不保存音频；不上传麦克风声音，不开启双向语音通话。火山引擎按其服务条款处理收到的文字。" },
          { term: "静态形象预览", text: "部署者可选展示 Live2D 官方经典 Miku 免费样例的静态预览图片。图片从本部署加载；点击官方来源链接会打开 Live2D 网站。教室的世界服装与动态模型待适配。" },
          { term: "运行记录", text: "保存请求时间、结果、模型用量和延迟等运行信息，不把访问口令或模型密钥写入记录。运行记录按系统保留期清理。" },
        ],
        notes: ["这是单人实验。持有访问口令的人进入同一同行者账户，请勿把口令分享给其他人。"],
      },
      {
        title: "模型服务与部署管理",
        items: [
          { term: "模型处理", text: "角色回复和对话标题由部署者配置的模型服务生成，相关对话和档案会发送给该服务。首版默认通过 OpenRouter 调用 Anthropic Claude，以实际部署配置为准。服务商的数据处理遵循其条款。" },
          { term: "主机访问", text: "账户界面只提供自己的对话和档案。具有主机或数据库管理权限的人能够读取持久化数据；本实验不提供端到端加密。" },
          { term: "备份", text: "私人部署每天将数据库快照加密后保存在主机的独立备份目录，每份保留 14 天。恢复需要部署者本机保存的备份密钥。它不能抵御整台主机及其磁盘同时丢失。" },
        ],
        notes: [],
      },
      {
        title: "删除与退出",
        items: [],
        notes: ["你可以在历史对话中删除旧对话，或在设置中删除全部个人数据并退出所有会话。已制作的备份副本会在保留期到期后删除；保留在你手里的导出文件需自行处理。重新用私人口令登录后会建立新的同行者账户。"],
      },
    ],
  },
  settings: {
    ...base.settings,
    categories: { ...base.settings.categories, profile: "同行者档案" },
    about: { ...base.settings.about, disclaimer: PRIVATE_WORK.scope },
    profile: {
      ...base.settings.profile,
      formOfAddressHint: "初音对你的叫法。你是同行者；留空时使用角色默认的称呼。",
      genderHint: "用于这次私人对话中的称呼与相处方式，不会改写角色设定或官方剧情。",
      genderDefault: "不指定",
    },
  },
  terms: {
    ...base.terms,
    items: [
      { term: "非官方私人实验", text: "本实验与《プロジェクトセカイ カラフルステージ！ feat. 初音ミク》及初音未来的版权方和官方没有关联，仅供私人体验，不用于商业推广。" },
      { term: "原创文字练习", text: "v0.1.1 仅有教室的世界初音未来与三幕原创文字练习，不提供正式剧情或歌曲；可选展示 Live2D 官方经典 Miku 免费样例的静态预览，教室的世界服装与动态模型待适配。AI 生成内容不代表官方设定。" },
      { term: "可选点击朗读", text: "配置后，点击朗读会将所选回复发送给火山引擎合成语音。本部署不保存音频、不上传麦克风声音、不开启双向语音通话；合成音色不代表官方角色音色，声音复刻须另行配置。" },
      ...base.terms.items.filter((item) => item.term !== "非官方的粉丝作品" && item.term !== "玩法：好感度、冷却和礼物"),
    ],
    lastUpdated: "最后更新：2026 年 10 月 19 日",
  },
};
