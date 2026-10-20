"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

import { ReadAloud, readAloudAvailable } from "@/lib/readAloud";
import { isProjectSekai } from "@/lib/work";

export function useReadAloud(conversationId: string | null, userId: string) {
  const [player] = useState(() => new ReadAloud());
  const state = useSyncExternalStore(player.subscribe, player.snapshot, player.snapshot);
  const [availability, setAvailability] = useState<"loading" | "ready" | "unconfigured" | "failed" | "disabled">("loading");

  useEffect(() => {
    if (!isProjectSekai) return;
    const request = new AbortController();
    setAvailability("loading");
    void readAloudAvailable(request.signal).then(
      (available) => { if (!request.signal.aborted) setAvailability(available); },
      () => { if (!request.signal.aborted) setAvailability("failed"); },
    );
    return () => request.abort();
  }, [userId]);

  useEffect(() => () => player.stop(), [player, conversationId, userId]);

  return isProjectSekai ? { player, state, availability, conversationId } : null;
}

export type ReadAloudControls = ReturnType<typeof useReadAloud>;
