"use client";

import { useEffect, useRef, useState, type RefObject } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { api } from "@/lib/api";
import { avatarAvailable } from "@/lib/privateAvatar";

export function PrivateAvatarPreview({ image, container }: {
  image: string | null; container: RefObject<HTMLDivElement | null>;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="ghost" size="sm" />}>形象预览</DialogTrigger>
      <DialogContent container={container} variant="preview">
        <DialogHeader>
          <DialogTitle>形象预览</DialogTitle>
          <DialogDescription>经典 Miku 旧版样例；不是教室的世界服装，不与朗读同步口型</DialogDescription>
        </DialogHeader>
        {open && <AvatarCanvas image={image} />}
        <p className="text-meta text-muted-foreground">
          动态模型来自公开第三方镜像，仅供本部署私人试用，模型与 SDK 非开源资产。
        </p>
        <a href="https://github.com/Exrick/blog/tree/64af2aa88b6313e269e99616d930f7ca07b61da8/live2d/assets/miku" target="_blank" rel="noopener noreferrer">经典 Miku 旧版样例来源</a>
      </DialogContent>
    </Dialog>
  );
}

type State = "loading" | "ready" | "unavailable" | "failed" | "reduced";
const STATUS: Record<State, string> = {
  loading: "正在加载动态预览；暂时显示静态形象。",
  ready: "动态预览已就绪，可移动指针或播放动作。",
  unavailable: "本部署未配置可用的动态样例，显示静态预览。",
  failed: "动态预览加载失败或浏览器不支持 WebGL，显示静态预览。关闭后可重新尝试。",
  reduced: "已按减少动态效果偏好显示静态预览。",
};

function AvatarCanvas({ image }: { image: string | null }) {
  const host = useRef<HTMLDivElement>(null);
  const player = useRef<{ destroy(): void; play(): void } | null>(null);
  const reduced = useMediaQuery("(prefers-reduced-motion: reduce)");
  const [state, setState] = useState<State>("loading");
  useEffect(() => {
    if (reduced) { setState("reduced"); return; }
    let closed = false;
    const abort = new AbortController();
    const timer = setTimeout(() => {
      closed = true;
      abort.abort();
      player.current?.destroy();
      player.current = null;
      setState("failed");
    }, 20_000);
    setState("loading");
    void (async () => {
      const response = await api("/api/private-avatar", { signal: abort.signal, cache: "no-store" });
      if (closed) return;
      if (!response.ok || !avatarAvailable(await response.json())) {
        if (!closed) setState("unavailable");
        return;
      }
      const { createAvatarRenderer } = await import("@/lib/privateAvatarRenderer");
      if (closed || !host.current) return;
      player.current = createAvatarRenderer(host.current,
        () => { if (!closed) setState("ready"); },
        () => { if (!closed) setState("failed"); });
    })().catch(() => { if (!closed) setState("failed"); }).finally(() => clearTimeout(timer));
    return () => {
      closed = true;
      clearTimeout(timer);
      abort.abort();
      player.current?.destroy();
      player.current = null;
    };
  }, [reduced]);

  return (
    <>
      <div className="relative h-[min(55dvh,30rem)] w-full overflow-hidden rounded-xl bg-muted">
        <div ref={host} className={`absolute inset-0 ${state === "ready" ? "" : "invisible"}`} />
        {state !== "ready" && (image
          // eslint-disable-next-line @next/next/no-img-element
          ? <img src={image} alt="经典初音未来样例静态预览" className="h-full w-full object-contain" />
          : <p className="flex h-full items-center justify-center text-body text-muted-foreground">初音未来</p>)}
      </div>
      <p role="status" className="text-meta text-muted-foreground">{STATUS[state]}</p>
      <Button variant="outline" disabled={state !== "ready"} onClick={() => player.current?.play()}>播放动作</Button>
    </>
  );
}
