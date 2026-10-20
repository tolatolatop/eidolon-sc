import { api, json } from "@/lib/api";

export type VoiceInputState = {
  phase: "idle" | "requesting" | "recording" | "transcribing" | "review" | "failed";
  seconds: number;
  text: string;
  error: string | null;
};

type Recorder = { start(): void; stop(): void; detach(): void; mimeType: string };
export type VoiceInputDependencies = {
  /** Monotonic milliseconds; injectable without changing browser recording behavior. */
  now?: () => number;
  mime(): string;
  media(): Promise<MediaStream>;
  recorder(stream: MediaStream, mime: string, data: (blob: Blob) => void, stopped: () => void, failed: () => void): Recorder;
  transcribe(blob: Blob, language: string, signal: AbortSignal): Promise<string>;
};

const browser: VoiceInputDependencies = {
  mime() {
    if (!window.isSecureContext) throw new Error("录音需要受信任的 HTTPS，请先信任本部署证书。");
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      throw new Error("此浏览器不支持录音输入，请使用新版 Chrome 或 Safari。");
    }
    const mime = ["audio/webm;codecs=opus", "audio/mp4"].find((value) => MediaRecorder.isTypeSupported(value));
    if (!mime) throw new Error("此浏览器没有支持的录音格式，请使用新版 Chrome 或 Safari。");
    return mime;
  },
  media: () => navigator.mediaDevices.getUserMedia({ audio: true }),
  recorder(stream, mime, data, stopped, failed) {
    const recorder = new MediaRecorder(stream, { mimeType: mime });
    recorder.ondataavailable = (event) => data(event.data);
    recorder.onstop = stopped;
    recorder.onerror = failed;
    return {
      start: () => recorder.start(250),
      stop: () => { if (recorder.state !== "inactive") recorder.stop(); },
      detach: () => { recorder.ondataavailable = recorder.onstop = recorder.onerror = null; },
      mimeType: recorder.mimeType || mime,
    };
  },
  async transcribe(blob, language, signal) {
    const result = await json<{ text: string; language: string }>(await api(
      `/api/voice-input/transcribe?language=${encodeURIComponent(language)}`,
      { method: "POST", headers: { "Content-Type": blob.type }, body: blob, signal },
    ));
    if (typeof result.text !== "string" || result.text.length > 4000) throw new Error("语音输入返回无效结果，请重试。");
    return result.text;
  },
};

const IDLE: VoiceInputState = { phase: "idle", seconds: 0, text: "", error: null };
const MAX_BYTES = 5 * 1024 * 1024;

/** Only creates editable review text. Sending and draft changes require another explicit click. */
export class VoiceRecorder {
  private state = IDLE;
  private listeners = new Set<() => void>();
  private generation = 0;
  private stream: MediaStream | null = null;
  private recorder: Recorder | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;
  private request: AbortController | null = null;

  constructor(private readonly dependencies: VoiceInputDependencies = browser) {}
  snapshot = (): VoiceInputState => this.state;
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  cancel = (): void => {
    this.generation++;
    this.request?.abort();
    this.request = null;
    this.recorder?.detach();
    this.recorder?.stop();
    this.recorder = null;
    this.release();
    this.update(IDLE);
  };

  private release(): void {
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
  }

  async start(language: "auto" | "zh" | "ja"): Promise<void> {
    this.cancel();
    const generation = this.generation;
    this.update({ ...IDLE, phase: "requesting" });
    try {
      const mime = this.dependencies.mime();
      const stream = await this.dependencies.media();
      if (generation !== this.generation) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }
      this.stream = stream;
      const chunks: Blob[] = [];
      let bytes = 0;
      const recorder = this.dependencies.recorder(stream, mime, (blob) => {
        if (generation !== this.generation) return;
        bytes += blob.size;
        if (bytes > MAX_BYTES) return this.fail("录音超过5MiB，请缩短后重试。");
        chunks.push(blob);
      }, () => {
        if (generation !== this.generation) return;
        this.release();
        this.recorder?.detach();
        this.recorder = null;
        void this.transcribe(new Blob(chunks, { type: recorder.mimeType }), language, generation);
      }, () => { if (generation === this.generation) this.fail("录音失败，请检查麦克风后重试。"); });
      this.recorder = recorder;
      recorder.start();
      this.update({ ...IDLE, phase: "recording" });
      const now = this.dependencies.now ?? (() => performance.now());
      const started = now();
      this.timer = setInterval(() => {
        const seconds = Math.min(30, Math.floor((now() - started) / 1000));
        this.update({ ...this.state, seconds });
        // Leave encoder padding and event-loop jitter below the server's hard 30s cap.
        if (seconds >= 29) this.stop();
      }, 200);
    } catch (error) {
      if (generation !== this.generation) return;
      this.fail(error instanceof Error && error.name === "NotAllowedError"
        ? "麦克风权限被拒绝，请在浏览器网站设置中允许麦克风。"
        : error instanceof Error && error.name === "NotFoundError"
          ? "没有找到麦克风，请连接麦克风后重试。"
          : error instanceof Error ? error.message : "无法开始录音，请检查麦克风。");
    }
  }

  stop = (): void => {
    if (this.state.phase !== "recording") return;
    this.update({ ...this.state, phase: "transcribing" });
    this.recorder?.stop();
    this.release();
  };

  edit = (text: string): void => {
    if (this.state.phase === "review") this.update({ ...this.state, text: text.slice(0, 4000) });
  };

  /** Appends to the draft as it exists at click time, preserving edits made during recording. */
  take = (append: (text: string) => boolean): boolean => {
    if (this.state.phase !== "review" || !this.state.text.trim()) return false;
    const text = this.state.text.trim();
    if (!append(text)) return false;
    this.cancel();
    return true;
  };

  private async transcribe(blob: Blob, language: string, generation: number): Promise<void> {
    if (!blob.size) return this.fail("没有录到声音，请重新录音。");
    const request = new AbortController();
    this.request = request;
    this.update({ ...this.state, phase: "transcribing" });
    try {
      const text = await this.dependencies.transcribe(blob, language, request.signal);
      if (generation !== this.generation) return;
      if (!text.trim()) return this.fail("没有识别到说话声，请靠近麦克风后重试。");
      this.update({ ...this.state, phase: "review", text });
    } catch (error) {
      if (generation !== this.generation) return;
      this.fail(error instanceof Error ? error.message : "语音输入失败，请稍后重试。");
    } finally {
      if (generation === this.generation) this.request = null;
    }
  }

  private fail(error: string): void {
    this.cancel();
    this.update({ ...IDLE, phase: "failed", error });
  }

  private update(state: VoiceInputState): void {
    this.state = state;
    this.listeners.forEach((listener) => listener());
  }
}

export function appendVoiceDraft(draft: string, text: string): string | null {
  const combined = [draft, text].filter(Boolean).join("\n");
  // LiveConversation.setDraft enforces the backend's 2,000-character message cap.
  // Refuse before calling it so neither the draft nor reviewed text is lost.
  return combined.length <= 2000 ? combined : null;
}
