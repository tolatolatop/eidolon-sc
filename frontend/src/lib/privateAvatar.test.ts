import { afterEach, describe, expect, it, vi } from "vitest";

import { avatarAvailable, avatarFit, AVATAR_MODEL, AVATAR_SCRIPT, createScriptLoader } from "./privateAvatar";

afterEach(() => vi.useRealTimers());

describe("private avatar boundary", () => {
  it("only accepts the fixed same-origin runtime and model endpoints", () => {
    const ready = { available: true, model_url: AVATAR_MODEL, script_url: AVATAR_SCRIPT };
    expect(avatarAvailable(ready)).toBe(true);
    for (const value of [null, {}, { ...ready, available: false },
      { ...ready, script_url: "https://example.com/sdk.js" },
      { ...ready, model_url: "/api/private-avatar/assets/other.json" }]) {
      expect(avatarAvailable(value)).toBe(false);
    }
  });

  it("shares concurrent loads and retains a successful runtime", async () => {
    let loaded = () => {};
    const remove = vi.fn();
    const append = vi.fn((success: () => void) => { loaded = success; return remove; });
    const load = createScriptLoader(append);
    const first = load();
    expect(load()).toBe(first);
    loaded();
    await first;
    expect(load()).toBe(first);
    expect(append).toHaveBeenCalledTimes(1);
    expect(remove).toHaveBeenCalledTimes(1);
  });

  it("removes failed and timed out scripts and permits a fresh attempt", async () => {
    vi.useFakeTimers();
    let fail = () => {};
    const remove = vi.fn();
    const load = createScriptLoader((_success, failure) => { fail = failure; return remove; }, 50);
    const first = load();
    const rejected = expect(first).rejects.toThrow("unavailable");
    fail();
    await rejected;
    const second = load();
    expect(second).not.toBe(first);
    const expired = expect(second).rejects.toThrow("unavailable");
    await vi.advanceTimersByTimeAsync(50);
    await expired;
    expect(remove).toHaveBeenCalledTimes(2);
  });

  it("contains the complete figure on narrow and short screens", () => {
    for (const [width, height] of [[300, 520], [600, 180], [1, 1]]) {
      const scale = avatarFit(width, height, 1000, 2000);
      expect(1000 * scale).toBeLessThanOrEqual(width);
      expect(2000 * scale).toBeLessThanOrEqual(height);
      expect(scale).toBeGreaterThan(0);
    }
  });
});
