"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { ReadAloud, readAloudAvailable } from "@/lib/readAloud";
import { isProjectSekai } from "@/lib/work";

export function useReadAloud(conversationId: string | null, userId: string) {
  const [player] = useState(() => new ReadAloud());
  const state = useSyncExternalStore(player.subscribe, player.snapshot, player.snapshot);
  const [availability, setAvailability] = useState<"loading" | "ready" | "unconfigured" | "unready" | "failed" | "disabled">("loading");

  const healthRequest = useRef<AbortController | null>(null);
  const [provider, setProvider] = useState<"kokoro" | "volcengine">("volcengine");

  const retryAvailability = useCallback(() => {
    healthRequest.current?.abort();
    if (!isProjectSekai) return;
    const request = new AbortController();
    healthRequest.current = request;
    setAvailability("loading");
    void readAloudAvailable(request.signal).then(
      (status) => {
        if (!request.signal.aborted) {
          setAvailability(status.availability);
          setProvider(status.provider);
        }
      },
      () => { if (!request.signal.aborted) setAvailability("failed"); },
    );
  }, []);

  useEffect(() => {
    retryAvailability();
    return () => healthRequest.current?.abort();
  }, [userId, retryAvailability]);

  useEffect(() => () => player.stop(), [player, conversationId, userId]);

  return isProjectSekai ? { player, state, availability, provider, conversationId, retryAvailability } : null;
}

export type ReadAloudControls = ReturnType<typeof useReadAloud>;
