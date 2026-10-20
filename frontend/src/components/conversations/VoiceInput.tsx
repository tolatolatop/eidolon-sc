"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api, json } from "@/lib/api";
import { VoiceRecorder } from "@/lib/voiceInput";

export function VoiceInput({ onAppend }: { onAppend: (text: string) => boolean }) {
  const [recorder] = useState(() => new VoiceRecorder());
  const state = useSyncExternalStore(recorder.subscribe, recorder.snapshot, recorder.snapshot);
  const [available, setAvailable] = useState(false);
  const [status, setStatus] = useState("正在检查本地语音输入…");

  useEffect(() => {
    const request = new AbortController();
    void api("/api/voice-input", { signal: request.signal }).then((response) => json<{ available: boolean; reason: string }>(response)).then(
      (result) => {
        if (request.signal.aborted) return;
        setAvailable(result.available);
        setStatus(result.available ? "" : result.reason === "unconfigured" ? "本部署尚未配置本地语音输入。" : "本地语音输入尚未就绪，请稍后刷新重试。");
      },
      () => { if (!request.signal.aborted) setStatus("暂时无法检查语音输入，请刷新重试。"); },
    );
    const cancel = () => recorder.cancel();
    window.addEventListener("pagehide", cancel);
    return () => {
      request.abort();
      window.removeEventListener("pagehide", cancel);
      recorder.cancel();
    };
  }, [recorder]);

  const active = ["requesting", "recording", "transcribing"].includes(state.phase);
  return <div className="flex flex-col gap-2">
    <div className="flex items-center gap-2">
      <Button type="button" variant="ghost" size="sm" disabled={!available || active || state.phase === "review"} onClick={() => { setStatus(""); void recorder.start("auto"); }}>录音输入</Button>
      {state.phase === "recording" && <Button type="button" variant="outline" size="sm" onClick={recorder.stop}>停止并转写</Button>}
      {(active || state.phase === "review") && <Button type="button" variant="ghost" size="sm" onClick={() => { recorder.cancel(); setStatus(""); }}>取消</Button>}
      {active && <span role="status" className="text-meta text-muted-foreground">{state.phase === "requesting" ? "请允许麦克风权限" : state.phase === "recording" ? `录音 ${state.seconds}/30秒` : "正在本地转写…"}</span>}
    </div>
    <p className="text-meta text-muted-foreground">最多30秒，录音时请保持本页在前台。录音上传到本部署 Whisper，在内存中处理，不保存音频。识别后先校对，再追加到草稿；点击发送后，文字仍会交给外部语言模型。</p>
    {(status || state.error) && <p role="status" className="text-meta text-muted-foreground">{state.error || status}</p>}
    {state.phase === "review" && <>
      <Textarea aria-label="校对识别文字" maxLength={4000} value={state.text} onChange={(event) => recorder.edit(event.target.value)} />
      <div className="flex items-center gap-2">
        <Button type="button" variant="outline" size="sm" disabled={!state.text.trim()} onClick={() => {
          setStatus(recorder.take(onAppend) ? "" : "合并后超过2000字，请先缩短识别文字或原有草稿；校对文字已保留。");
        }}>追加填入草稿</Button>
        <span className="text-meta text-muted-foreground">保留原有草稿，不会自动发送。</span>
      </div>
    </>}
  </div>;
}
