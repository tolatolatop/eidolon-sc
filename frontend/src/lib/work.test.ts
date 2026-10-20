import { afterEach, describe, expect, it, vi } from "vitest";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("work selection", () => {
  it("preserves the original work when no work is selected", async () => {
    vi.stubEnv("NEXT_PUBLIC_EIDOLON_WORK", "");
    vi.resetModules();
    const { copy } = await import("@/i18n");
    const { zh } = await import("@/i18n/zh");
    expect(copy).toBe(zh);
  });

  it("selects the private companion identity consistently on the client and server", async () => {
    vi.stubEnv("NEXT_PUBLIC_EIDOLON_WORK", "project-sekai");
    vi.resetModules();
    const { copy } = await import("@/i18n");
    expect(copy.app.name).toBe("同行 · 教室的世界");
    expect(copy.legal.pageTitle("使用条款")).toBe(`使用条款 · ${copy.app.name}`);
    expect(copy.settings.categories.profile).toBe("同行者档案");
    expect(copy.settings.profile.formOfAddressHint).not.toContain("制作人");
    expect(copy.login.lede).not.toMatch(/283|闪耀色彩|自己的声音|回忆.*原作/);
    expect(copy.terms.items.some((item) => item.text.includes("正式剧情"))).toBe(true);
    expect(copy.settings.dataPackage.importedWithProfile("2 段对话")).toContain("同行者档案");
    expect(copy.privacy.sections.flatMap((section) => JSON.stringify(section)).join("")).not.toContain("制作人");
  });

  it("ignores an old SCSP avatar preference in the private work", async () => {
    vi.stubEnv("NEXT_PUBLIC_EIDOLON_WORK", "project-sekai");
    vi.resetModules();
    const { withAppearance } = await import("./appearance");
    const characters: import("./api").Character[] = [{ id: "miku-school", name: "初音未来", intro: "", color: "#33ccbb", avatar_url: null, scsp_avatar_url: "/old-media", background_url: null, stand: null, idol_id: null, name_zh: null, name_kana: null, name_romaji: null, unit: null, unit_reading: null, unit_order: null, greeting: null, call_opener: null, call_poster_url: null, voxels_url: null }];
    expect(withAppearance(characters, { scspAvatars: true })).toBe(characters);
  });

  it("describes local transcription and explicit external text processing consistently", async () => {
    const { PRIVATE_WORK } = await import("./work");
    const { projectSekai } = await import("@/i18n/projectSekai");
    expect(PRIVATE_WORK.label).toContain("v0.1.3");
    expect(PRIVATE_WORK.scope).toContain("静态预览");
    expect(PRIVATE_WORK.appearance).toContain("动态预览");
    expect(PRIVATE_WORK.appearance).toContain("不是教室的世界服装");
    expect(PRIVATE_WORK.scope).toContain("模型与 SDK 非开源资产");
    for (const text of [
      projectSekai.consent.intro,
      JSON.stringify(projectSekai.privacy.sections), JSON.stringify(projectSekai.terms.items),
    ]) {
      expect(text).toContain("Whisper");
      expect(text).toContain("不保存音频");
      expect(text).toContain("外部语言模型");
      expect(text).toContain("本部署 Kokoro");
      expect(text).toContain("非官方角色声音");
      expect(text).toContain("没有克隆初音未来的声音");
      expect(text).toContain("30秒");
      expect(text).toContain("双向语音通话");
      expect(text).not.toMatch(/只开放文字对话|未启用语音/);
    }
  });
});
