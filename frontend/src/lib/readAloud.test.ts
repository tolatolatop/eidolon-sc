import { describe, expect, it, vi } from "vitest";

import { ReadAloud, savedReplyId, type ReadAloudDependencies } from "./readAloud";

function setup() {
  const audio = {
    src: "", play: vi.fn(async () => {}), pause: vi.fn(), load: vi.fn(),
    onended: null as (() => void) | null,
    onerror: null as (() => void) | null,
  };
  const dependencies = {
    synthesize: vi.fn<ReadAloudDependencies["synthesize"]>(async () => new Blob(["mp3"], { type: "audio/mpeg" })),
    audio: vi.fn(() => audio),
    createURL: vi.fn(() => "blob:one"),
    revokeURL: vi.fn(),
  } satisfies ReadAloudDependencies;
  return { player: new ReadAloud(dependencies), dependencies, audio };
}

describe("explicit reply read-aloud", () => {
  it("does not synthesize or play until clicked, and stops/reclaims URL on another click", async () => {
    const { player, dependencies, audio } = setup();
    expect(dependencies.synthesize).not.toHaveBeenCalled();
    await player.toggle("conversation", 12);
    expect(dependencies.synthesize).toHaveBeenCalledWith("conversation", 12, expect.any(AbortSignal));
    expect(audio.play).toHaveBeenCalledOnce();
    expect(player.snapshot()).toMatchObject({ messageId: 12, phase: "playing" });
    await player.toggle("conversation", 12);
    expect(audio.pause).toHaveBeenCalledOnce();
    expect(audio.src).toBe("");
    expect(dependencies.revokeURL).toHaveBeenCalledWith("blob:one");
    expect(player.snapshot().phase).toBe("idle");
  });

  it("aborts an in-flight synthesis and ignores late audio after navigating away", async () => {
    const { dependencies, audio } = setup();
    let resolve!: (blob: Blob) => void;
    let signal: AbortSignal | undefined;
    dependencies.synthesize = vi.fn((_conversation, _message, request) => {
      signal = request;
      return new Promise<Blob>((done) => { resolve = done; });
    });
    const player = new ReadAloud(dependencies);
    const request = player.toggle("conversation", 12);
    expect(player.snapshot().phase).toBe("loading");
    player.stop();
    expect(signal?.aborted).toBe(true);
    resolve(new Blob(["late"]));
    await request;
    expect(dependencies.createURL).not.toHaveBeenCalled();
    expect(audio.play).not.toHaveBeenCalled();
    expect(player.snapshot().phase).toBe("idle");
  });

  it("switching replies stops the old audio and releases its URL", async () => {
    const { player, dependencies, audio } = setup();
    await player.toggle("conversation", 12);
    await player.toggle("conversation", 15);
    expect(audio.pause).toHaveBeenCalledOnce();
    expect(dependencies.revokeURL).toHaveBeenCalledOnce();
    expect(player.snapshot().messageId).toBe(15);
    audio.onended?.();
    expect(dependencies.revokeURL).toHaveBeenCalledTimes(2);
    expect(player.snapshot().phase).toBe("idle");
  });

  it("shows upstream failures and releases audio on rejected browser playback", async () => {
    const { dependencies, audio } = setup();
    audio.play.mockRejectedValueOnce(new Error("浏览器拒绝播放，请重试"));
    const player = new ReadAloud(dependencies);
    await player.toggle("conversation", 12);
    expect(player.snapshot()).toMatchObject({ phase: "failed", error: "浏览器拒绝播放，请重试" });
    expect(dependencies.revokeURL).toHaveBeenCalledOnce();
    dependencies.synthesize.mockRejectedValueOnce(new Error("朗读待配置"));
    await player.toggle("conversation", 15);
    expect(player.snapshot()).toMatchObject({ phase: "failed", error: "朗读待配置" });
  });

  it("retains downloaded audio after gesture denial and retries play without another paid request", async () => {
    const { dependencies, audio } = setup();
    audio.play.mockRejectedValueOnce(new DOMException("User activation required", "NotAllowedError"));
    const player = new ReadAloud(dependencies);
    await player.toggle("conversation", 12);
    expect(player.snapshot()).toMatchObject({ messageId: 12, phase: "ready" });
    expect(dependencies.revokeURL).not.toHaveBeenCalled();
    const retry = player.toggle("conversation", 12);
    // No await/network boundary before the second play call.
    expect(audio.play).toHaveBeenCalledTimes(2);
    await retry;
    expect(dependencies.synthesize).toHaveBeenCalledOnce();
    expect(dependencies.createURL).toHaveBeenCalledOnce();
    expect(player.snapshot().phase).toBe("playing");
    player.stop();
    expect(dependencies.revokeURL).toHaveBeenCalledOnce();
  });

  it("reclaims gesture-blocked audio on switching replies or leaving the page", async () => {
    const { player, dependencies, audio } = setup();
    audio.play.mockRejectedValueOnce(new DOMException("Blocked", "NotAllowedError"));
    await player.toggle("conversation", 12);
    await player.toggle("conversation", 15);
    expect(dependencies.revokeURL).toHaveBeenCalledOnce();
    expect(player.snapshot()).toMatchObject({ messageId: 15, phase: "playing" });
    player.stop();
    expect(dependencies.revokeURL).toHaveBeenCalledTimes(2);
  });

  it("accepts IDs only for complete persisted replies", () => {
    expect(savedReplyId("m12", false)).toBe(12);
    expect(savedReplyId("m12", true)).toBeNull();
    for (const key of ["new-12", "e12", "m0", "m-1", "mNaN", "m9999999999999999999"]) {
      expect(savedReplyId(key, false)).toBeNull();
    }
  });
});
