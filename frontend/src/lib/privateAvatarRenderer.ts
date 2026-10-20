import { avatarFit, AVATAR_MODEL, loadAvatarScript } from "./privateAvatar";

let textureSequence = 0;

/** Own every resource for one open dialog; imports and model responses may arrive after close. */
export function createAvatarRenderer(host: HTMLElement, ready: () => void, failed: () => void) {
  let disposed = false;
  let destroy = () => {};
  let play = () => {};
  const timer = setTimeout(() => { if (!disposed) { stop(); failed(); } }, 20_000);
  function stop() {
    if (disposed) return;
    disposed = true;
    clearTimeout(timer);
    destroy();
  }

  void (async () => {
    await loadAvatarScript();
    if (disposed) return;
    const [PIXI, { install }, live2d] = await Promise.all([
      import("pixi.js"), import("@pixi/unsafe-eval"), import("pixi-live2d-display/cubism2"),
    ]);
    if (disposed) return;
    // Official static uniform polyfill must be installed before constructing a renderer.
    install({ ShaderSystem: PIXI.ShaderSystem });
    live2d.Live2DModel.registerTicker(PIXI.Ticker);
    const model = new live2d.Live2DModel({ autoUpdate: false, autoInteract: false });
    let app: InstanceType<typeof PIXI.Application> | undefined;
    let settled = false;
    let destroyedModel = false;
    let cancelSetup = () => {};
    const cancelled = new Promise<void>((resolve) => { cancelSetup = resolve; });
    const modelURL = new URL(AVATAR_MODEL, location.origin).href;
    const texture = new URL("miku.2048/texture_00.png", modelURL);
    // PIXI caches textures globally by URL. Separate owners so an old cancelled load
    // cannot destroy a later dialog's texture. The API still serves the same fixed file.
    texture.searchParams.set("preview", String(++textureSequence));
    const textureURL = texture.href;
    model.once("settingsLoaded", (settings: { textures: string[] }) => {
      settings.textures = [textureURL];
    });
    const destroyModel = () => {
      if (destroyedModel) return;
      // Keep the late modelLoaded listener until there is a native model to release.
      if (model.internalModel) {
        destroyedModel = true;
        model.destroy({ children: true, texture: true, baseTexture: true });
      }
      const texture = PIXI.utils.TextureCache[textureURL];
      if (texture) texture.destroy(true);
    };
    // A model may arrive after cancellation while its texture promise never settles.
    model.once("modelLoaded", () => { if (disposed) destroyModel(); });
    const observer = new ResizeObserver(() => resize());
    const motion = matchMedia("(prefers-reduced-motion: reduce)");
    const active = () => !disposed && !motion.matches && !document.hidden;
    const update = (delta: number) => {
      model.update(delta * (1000 / 60));
    };
    function pause() {
      if (!app) return;
      if (active()) app.start();
      else app.stop();
    }
    function resize() {
      if (!app || disposed) return;
      const width = Math.max(1, host.clientWidth);
      const height = Math.max(1, host.clientHeight);
      app.renderer.resize(width, height);
      model.scale.set(avatarFit(width, height, model.internalModel.width, model.internalModel.height));
      model.position.set(width / 2, height / 2);
      app.render();
    }
    const pointer = (event: PointerEvent) => {
      if (!app || !active()) return;
      const rect = host.getBoundingClientRect();
      model.focus(event.clientX - rect.left, event.clientY - rect.top);
    };
    const lost = (event: Event) => {
      event.preventDefault();
      if (!disposed) { stop(); failed(); }
    };
    destroy = () => {
      cancelSetup();
      observer.disconnect();
      document.removeEventListener("visibilitychange", pause);
      motion.removeEventListener("change", pause);
      host.removeEventListener("pointermove", pointer);
      if (app) {
        app.view.removeEventListener?.("webglcontextlost", lost);
        const gl = app.renderer instanceof PIXI.Renderer ? app.renderer.gl : null;
        app.ticker.remove(update);
        app.stop();
        // The model is destroyed separately so textures are released even on partial loading.
        app.stage.removeChildren();
        destroyModel();
        app.destroy(true, { children: true });
        gl?.getExtension("WEBGL_lose_context")?.loseContext();
        app = undefined;
      } else {
        // Abort the plugin's outstanding XHRs. It cannot destroy a partially initialized model.
        model.emit("destroy");
        // The real destroy() also releases motionManager and its preloaded XHRs.
        if (model.internalModel || settled) destroyModel();
        const texture = PIXI.utils.TextureCache[textureURL];
        if (texture) texture.destroy(true);
      }
    };
    try {
      const setup = live2d.Live2DFactory.setupLive2DModel(model, modelURL, {
        autoUpdate: false, autoInteract: false,
      });
      const finish = () => {
        settled = true;
        if (disposed) destroyModel();
      };
      void setup.then(finish, finish).catch(() => {});
      await Promise.race([setup, cancelled]);
      if (disposed) { if (model.internalModel || settled) destroyModel(); return; }
      app = new PIXI.Application({
        width: Math.max(1, host.clientWidth), height: Math.max(1, host.clientHeight),
        backgroundAlpha: 0, antialias: true, autoStart: false,
        resolution: Math.min(devicePixelRatio || 1, 2), autoDensity: true,
      });
      model.anchor.set(0.5);
      app.stage.addChild(model);
      app.ticker.add(update);
      const canvas = app.view as HTMLCanvasElement;
      canvas.setAttribute("aria-label", "经典初音未来 Cubism2 动态预览");
      canvas.setAttribute("role", "img");
      canvas.addEventListener("webglcontextlost", lost);
      host.append(canvas);
      host.addEventListener("pointermove", pointer);
      observer.observe(host);
      document.addEventListener("visibilitychange", pause);
      motion.addEventListener("change", pause);
      play = () => {
        if (active()) void model.motion("null", 0, live2d.MotionPriority.NORMAL).catch(() => {});
      };
      resize();
      pause();
      clearTimeout(timer);
      ready();
    } catch {
      settled = true;
      if (!disposed) { stop(); failed(); }
      else destroyModel();
    }
  })().catch(() => { if (!disposed) { stop(); failed(); } });
  return { destroy: stop, play: () => play() };
}
