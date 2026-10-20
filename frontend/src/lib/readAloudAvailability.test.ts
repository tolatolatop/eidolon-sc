import { afterEach, expect, it, vi } from "vitest";

import { readAloudAvailable } from "./readAloud";

afterEach(() => vi.unstubAllGlobals());

it.each([
  [{ available: true, provider: "kokoro" }, { availability: "ready", provider: "kokoro" }],
  [{ available: false, provider: "kokoro", reason: "unready" }, { availability: "unready", provider: "kokoro" }],
  [{ available: false }, { availability: "unconfigured", provider: "volcengine" }],
  [{ available: true }, { availability: "ready", provider: "volcengine" }],
  [{ available: false, enabled: false }, { availability: "disabled", provider: "volcengine" }],
])("distinguishes actual local readiness from missing cloud configuration (%j)", async (body, expected) => {
  const fetch = vi.fn(async () => Response.json(body));
  vi.stubGlobal("fetch", fetch);
  const controller = new AbortController();
  expect(await readAloudAvailable(controller.signal)).toEqual(expected);
  expect(fetch).toHaveBeenCalledWith("/api/read-aloud", expect.objectContaining({ signal: controller.signal }));
});

it("allows an explicit cancelled health check to be retried without background requests", async () => {
  const fetch = vi.fn()
    .mockImplementationOnce((_url: string, init: RequestInit) => new Promise<Response>((_resolve, reject) => {
      init.signal?.addEventListener("abort", () => reject(new DOMException("Cancelled", "AbortError")), { once: true });
    }))
    .mockResolvedValueOnce(Response.json({ available: true, provider: "kokoro" }));
  vi.stubGlobal("fetch", fetch);
  const oldRequest = new AbortController();
  const pending = readAloudAvailable(oldRequest.signal);
  const cancelled = expect(pending).rejects.toMatchObject({ name: "AbortError" });
  oldRequest.abort();
  const nextRequest = new AbortController();
  expect(await readAloudAvailable(nextRequest.signal)).toEqual({ availability: "ready", provider: "kokoro" });
  await cancelled;
  await Promise.resolve();
  expect(fetch).toHaveBeenCalledTimes(2);
});
