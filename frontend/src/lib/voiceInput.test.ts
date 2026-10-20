import { afterEach, describe, expect, it, vi } from "vitest";

import { appendVoiceDraft, VoiceRecorder, type VoiceInputDependencies } from "./voiceInput";

afterEach(() => vi.useRealTimers());

function setup() {
  const stopTrack = vi.fn();
  const stream = { getTracks: () => [{ stop: stopTrack }] } as unknown as MediaStream;
  let data: (blob: Blob) => void = () => {};
  let stopped: () => void = () => {};
  const handle = { start: vi.fn(), stop: vi.fn(() => { data(new Blob(["audio"])); stopped(); }), detach: vi.fn(), mimeType: "audio/webm;codecs=opus" };
  const dependencies = {
    mime: () => "audio/webm;codecs=opus",
    media: vi.fn(async () => stream),
    recorder: vi.fn<VoiceInputDependencies["recorder"]>((_stream, _mime, onData, onStop) => {
      data = onData; stopped = onStop; return handle;
    }),
    transcribe: vi.fn<VoiceInputDependencies["transcribe"]>(async () => "识别文字"),
  } satisfies VoiceInputDependencies;
  return { recorder: new VoiceRecorder(dependencies), dependencies, handle, stopTrack, stream };
}

describe("local recording review", () => {
  it("requests microphone only on start, stops tracks, and waits for review before changing draft", async () => {
    const { recorder, dependencies, stopTrack } = setup();
    expect(dependencies.media).not.toHaveBeenCalled();
    expect(dependencies.transcribe).not.toHaveBeenCalled();
    await recorder.start("auto");
    expect(recorder.snapshot().phase).toBe("recording");
    recorder.stop();
    await Promise.resolve();
    expect(stopTrack).toHaveBeenCalled();
    expect(recorder.snapshot()).toMatchObject({ phase: "review", text: "识别文字" });
    const originalDraft = "原有草稿";
    expect(originalDraft).toBe("原有草稿");
    recorder.edit("校对后的文字");
    let nextDraft = originalDraft;
    expect(recorder.take((text) => {
      nextDraft = appendVoiceDraft(originalDraft, text) ?? originalDraft;
      return true;
    })).toBe(true);
    expect(nextDraft).toBe("原有草稿\n校对后的文字");
    expect(recorder.take(() => true)).toBe(false);
  });

  it("stops before thirty seconds with encoder headroom and supports Safari mp4", async () => {
    vi.useFakeTimers();
    const { recorder, dependencies, handle, stopTrack } = setup();
    dependencies.mime = () => "audio/mp4";
    handle.mimeType = "audio/mp4";
    await recorder.start("ja");
    await vi.advanceTimersByTimeAsync(30000);
    expect(handle.stop).toHaveBeenCalledOnce();
    expect(stopTrack).toHaveBeenCalled();
    expect(dependencies.transcribe.mock.calls[0][0].type).toBe("audio/mp4");
    expect(dependencies.transcribe.mock.calls[0][1]).toBe("ja");
    expect(recorder.snapshot().phase).toBe("review");
  });

  it("keeps the recording deadline when the wall clock moves backwards", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-20T12:00:00Z"));
    const { recorder, handle } = setup();
    await recorder.start("auto");
    await vi.advanceTimersByTimeAsync(10000);
    expect(recorder.snapshot()).toMatchObject({ phase: "recording", seconds: 10 });
    vi.setSystemTime(new Date("2026-10-20T11:00:00Z"));
    await vi.advanceTimersByTimeAsync(19000);
    expect(handle.stop).toHaveBeenCalledOnce();
    expect(recorder.snapshot().phase).toBe("review");
  });

  it("cancel while waiting for permission releases a late microphone stream", async () => {
    const { dependencies, stream, stopTrack } = setup();
    let resolve!: (stream: MediaStream) => void;
    dependencies.media = vi.fn(() => new Promise<MediaStream>((done) => { resolve = done; }));
    const recorder = new VoiceRecorder(dependencies);
    const start = recorder.start("auto");
    recorder.cancel();
    resolve(stream);
    await start;
    expect(stopTrack).toHaveBeenCalledOnce();
    expect(dependencies.recorder).not.toHaveBeenCalled();
    expect(recorder.snapshot().phase).toBe("idle");
  });

  it("aborts transcription and ignores late results after conversation changes or leaving", async () => {
    const { dependencies } = setup();
    let resolve!: (text: string) => void;
    dependencies.transcribe = vi.fn(() => new Promise<string>((done) => { resolve = done; }));
    const recorder = new VoiceRecorder(dependencies);
    await recorder.start("zh");
    recorder.stop();
    const signal = dependencies.transcribe.mock.calls[0][2];
    recorder.cancel();
    expect(signal.aborted).toBe(true);
    resolve("迟到文字");
    await Promise.resolve();
    expect(recorder.snapshot()).toMatchObject({ phase: "idle", text: "" });
    expect(recorder.take(() => true)).toBe(false);
  });

  it("cancel recording detaches callbacks and releases tracks without transcribing", async () => {
    const { recorder, dependencies, stopTrack, handle } = setup();
    await recorder.start("auto");
    recorder.cancel();
    expect(handle.detach).toHaveBeenCalled();
    expect(stopTrack).toHaveBeenCalled();
    expect(dependencies.transcribe).not.toHaveBeenCalled();
    expect(recorder.snapshot().phase).toBe("idle");
  });

  it("reports microphone refusal, unsupported browser, silence and service errors", async () => {
    const { dependencies } = setup();
    dependencies.media.mockRejectedValueOnce(Object.assign(new Error("denied"), { name: "NotAllowedError" }));
    const recorder = new VoiceRecorder(dependencies);
    await recorder.start("auto");
    expect(recorder.snapshot().error).toContain("权限被拒绝");
    dependencies.transcribe.mockResolvedValueOnce("");
    await recorder.start("auto"); recorder.stop(); await Promise.resolve();
    expect(recorder.snapshot().error).toContain("没有识别到");
    dependencies.transcribe.mockRejectedValueOnce(new Error("本地服务尚未就绪"));
    await recorder.start("auto"); recorder.stop(); await Promise.resolve();
    expect(recorder.snapshot().error).toBe("本地服务尚未就绪");
    dependencies.mime = () => { throw new Error("不支持录音"); };
    await recorder.start("auto");
    expect(recorder.snapshot().error).toBe("不支持录音");
  });

  it("keeps both the existing draft and reviewed text when appending would exceed the message cap", async () => {
    const { recorder } = setup();
    await recorder.start("auto");
    recorder.stop();
    await Promise.resolve();
    const original = "字".repeat(2000);
    const accepted = recorder.take((text) => appendVoiceDraft(original, text) !== null);
    expect(accepted).toBe(false);
    expect(original).toHaveLength(2000);
    expect(recorder.snapshot()).toMatchObject({ phase: "review", text: "识别文字" });
  });
});
