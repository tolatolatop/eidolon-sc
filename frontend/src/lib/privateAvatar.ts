/** Fixed same-origin endpoints: never execute a script URL supplied by an API response. */
export const AVATAR_MODEL = "/api/private-avatar/assets/miku.model.json";
export const AVATAR_SCRIPT = "/api/private-avatar/assets/live2d.min.js";

export function avatarAvailable(value: unknown): boolean {
  return typeof value === "object" && value !== null
    && "available" in value && value.available === true
    && "model_url" in value && value.model_url === AVATAR_MODEL
    && "script_url" in value && value.script_url === AVATAR_SCRIPT;
}

/** One shared script attempt; a failed/expired attempt leaves the next open free to retry. */
export function createScriptLoader(append: (success: () => void, failure: () => void) => () => void,
  timeoutMs = 12_000) {
  let pending: Promise<void> | undefined;
  return () => {
    if (pending) return pending;
    const attempt = new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => finish(false), timeoutMs);
      let remove = () => {};
      let finished = false;
      function finish(ok: boolean) {
        if (finished) return;
        finished = true;
        clearTimeout(timer);
        remove();
        if (ok) resolve();
        else reject(new Error("Cubism runtime unavailable"));
      }
      remove = append(() => finish(true), () => finish(false));
    });
    pending = attempt;
    void attempt.catch(() => { if (pending === attempt) pending = undefined; });
    return attempt;
  };
}

export const loadAvatarScript = createScriptLoader((success, failure) => {
  const script = document.createElement("script");
  script.src = AVATAR_SCRIPT;
  script.async = true;
  script.onload = success;
  script.onerror = failure;
  document.head.append(script);
  return () => { script.onload = script.onerror = null; script.remove(); };
});

/** Contain the complete figure, with space around the edges in portrait and landscape. */
export function avatarFit(width: number, height: number, modelWidth: number, modelHeight: number) {
  return Math.min(Math.max(1, width) / Math.max(1, modelWidth),
    Math.max(1, height) / Math.max(1, modelHeight)) * 0.94;
}
