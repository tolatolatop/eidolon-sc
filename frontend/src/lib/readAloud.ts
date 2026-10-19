import { api, json } from "@/lib/api";

export type ReadAloudState = {
  messageId: number | null;
  phase: "idle" | "loading" | "ready" | "playing" | "failed";
  error: string | null;
};

type AudioHandle = Pick<HTMLAudioElement, "play" | "pause" | "src" | "onended" | "onerror" | "load">;
export type ReadAloudDependencies = {
  synthesize: (conversationId: string, messageId: number, signal: AbortSignal) => Promise<Blob>;
  audio: () => AudioHandle;
  createURL: (blob: Blob) => string;
  revokeURL: (url: string) => void;
};

const browser: ReadAloudDependencies = {
  async synthesize(conversationId, messageId, signal) {
    const response = await api(
      `/api/conversations/${encodeURIComponent(conversationId)}/messages/${messageId}/read-aloud`,
      { method: "POST", signal },
    );
    if (!response.ok) await json(response);
    return response.blob();
  },
  audio: () => new Audio(),
  createURL: (blob) => URL.createObjectURL(blob),
  revokeURL: (url) => URL.revokeObjectURL(url),
};

const IDLE: ReadAloudState = { messageId: null, phase: "idle", error: null };

/** One explicitly requested reply at a time. Cancellation invalidates late fetch/play results. */
export class ReadAloud {
  private state = IDLE;
  private listeners = new Set<() => void>();
  private request: AbortController | null = null;
  private audio: AudioHandle | null = null;
  private url: string | null = null;
  private generation = 0;

  constructor(private readonly dependencies: ReadAloudDependencies = browser) {}

  snapshot = (): ReadAloudState => this.state;
  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  stop = (): void => {
    this.generation++;
    this.request?.abort();
    this.request = null;
    if (this.audio) {
      this.audio.onended = this.audio.onerror = null;
      this.audio.pause();
      this.audio.src = "";
      this.audio.load();
      this.audio = null;
    }
    if (this.url) this.dependencies.revokeURL(this.url);
    this.url = null;
    this.update(IDLE);
  };

  async toggle(conversationId: string, messageId: number): Promise<void> {
    // Call play() synchronously from the second click, before any network wait,
    // so Safari can use that click's activation without buying the audio again.
    if (this.state.messageId === messageId && this.state.phase === "ready" && this.audio) {
      return this.play(messageId);
    }
    const stopping = this.state.messageId === messageId && ["loading", "playing"].includes(this.state.phase);
    this.stop();
    if (stopping) return;
    const generation = this.generation;
    const request = new AbortController();
    this.request = request;
    this.update({ messageId, phase: "loading", error: null });
    try {
      const blob = await this.dependencies.synthesize(conversationId, messageId, request.signal);
      if (this.generation !== generation) return;
      this.url = this.dependencies.createURL(blob);
      const audio = this.dependencies.audio();
      this.audio = audio;
      audio.src = this.url;
      audio.onended = () => this.stop();
      audio.onerror = () => this.failed(messageId, "音频播放失败，请重试");
      await this.play(messageId);
    } catch (error) {
      if (this.generation !== generation) return;
      this.failed(messageId, error instanceof Error ? error.message : "朗读失败，请稍后重试");
    }
  }

  private async play(messageId: number): Promise<void> {
    const audio = this.audio;
    if (!audio) return;
    const generation = this.generation;
    try {
      await audio.play();
      if (this.generation === generation) this.update({ messageId, phase: "playing", error: null });
    } catch (error) {
      if (this.generation !== generation) return;
      if (error instanceof Error && error.name === "NotAllowedError") {
        this.update({ messageId, phase: "ready", error: "语音已生成，请点击「播放朗读」。" });
      } else {
        this.failed(messageId, error instanceof Error ? error.message : "音频播放失败，请重试");
      }
    }
  }

  private failed(messageId: number, error: string): void {
    this.stop();
    this.update({ messageId, phase: "failed", error });
  }

  private update(state: ReadAloudState): void {
    this.state = state;
    this.listeners.forEach((listener) => listener());
  }
}

export async function readAloudAvailable(signal: AbortSignal): Promise<boolean> {
  const status = await json<{ available: boolean }>(await api("/api/read-aloud", { signal }));
  return status.available;
}

/** Pending replies use temporary keys; only persisted, complete replies have message IDs. */
export function savedReplyId(key: string, pending: boolean): number | null {
  if (pending || !/^m[1-9]\d*$/.test(key)) return null;
  const id = Number(key.slice(1));
  return Number.isSafeInteger(id) ? id : null;
}
