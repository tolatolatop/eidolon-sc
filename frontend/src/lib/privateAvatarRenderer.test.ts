import { afterEach, beforeEach, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({
  sdk: Promise.resolve(), model: Promise.resolve(),
  setup: vi.fn(), construct: vi.fn(), release: vi.fn(),
  start: vi.fn(), stop: vi.fn(), destroyApp: vi.fn(), lose: vi.fn(),
  resize: vi.fn(), disconnect: vi.fn(),
  partial: false,
}));

vi.mock("./privateAvatar", async (original) => ({
  ...await original<typeof import("./privateAvatar")>(),
  loadAvatarScript: () => state.sdk,
}));
vi.mock("@pixi/unsafe-eval", () => ({ install: vi.fn() }));
vi.mock("pixi-live2d-display/cubism2", () => ({
  Live2DModel: class {
    static registerTicker = vi.fn();
    internalModel: object | undefined;
    anchor = { set: vi.fn() }; scale = { set: vi.fn() }; position = { set: vi.fn() };
    emit = vi.fn(); once = vi.fn(); destroy = state.release; update = vi.fn(); focus = vi.fn();
    motion = vi.fn(async () => true);
  },
  MotionPriority: { NORMAL: 2 },
  Live2DFactory: {
    setupLive2DModel: async (model: { internalModel: object | undefined }) => {
      state.setup();
      if (state.partial) model.internalModel = { width: 100, height: 200, emit: vi.fn() };
      await state.model;
      model.internalModel = { width: 100, height: 200, emit: vi.fn() };
    },
  },
}));
vi.mock("pixi.js", () => {
  class Renderer {
    gl = { getExtension: () => ({ loseContext: state.lose }) };
    resize = state.resize;
  }
  return {
    ShaderSystem: class {}, Ticker: class {}, Renderer,
    Container: class { destroy = state.release; },
    utils: { TextureCache: {} },
    Application: class {
      constructor() { state.construct(); }
      renderer = new Renderer();
      view = { setAttribute: vi.fn(), addEventListener: vi.fn(), removeEventListener: vi.fn() };
      stage = { addChild: vi.fn(), removeChildren: vi.fn() };
      ticker = { add: vi.fn(), remove: vi.fn() };
      render = vi.fn(); start = state.start; stop = state.stop; destroy = state.destroyApp;
    },
  };
});

import { createAvatarRenderer } from "./privateAvatarRenderer";

let visibility: () => void;
const doc = { hidden: false, addEventListener: (_name: string, callback: () => void) => { visibility = callback; }, removeEventListener: vi.fn() };
const host = {
  clientWidth: 300, clientHeight: 200, append: vi.fn(),
  addEventListener: vi.fn(), removeEventListener: vi.fn(),
} as unknown as HTMLElement;

beforeEach(() => {
  vi.clearAllMocks();
  state.sdk = Promise.resolve(); state.model = Promise.resolve(); doc.hidden = false;
  state.partial = false;
  vi.stubGlobal("ResizeObserver", class { observe = vi.fn(); disconnect = state.disconnect; });
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
  vi.stubGlobal("document", doc);
  vi.stubGlobal("location", { origin: "https://private.example" });
  vi.stubGlobal("devicePixelRatio", 2);
});
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

it("allocates no renderer when a shared SDK resolves after close", async () => {
  let resolve = () => {};
  state.sdk = new Promise<void>((done) => { resolve = done; });
  const ready = vi.fn(), failed = vi.fn();
  const owner = createAvatarRenderer(host, ready, failed);
  owner.destroy();
  resolve();
  await state.sdk;
  await Promise.resolve();
  expect(state.setup).not.toHaveBeenCalled();
  expect(state.construct).not.toHaveBeenCalled();
  expect(ready).not.toHaveBeenCalled();
  expect(failed).not.toHaveBeenCalled();
});

it("ends loading at the deadline and ignores a late SDK response", async () => {
  vi.useFakeTimers();
  let resolve = () => {};
  state.sdk = new Promise<void>((done) => { resolve = done; });
  const ready = vi.fn(), failed = vi.fn();
  const owner = createAvatarRenderer(host, ready, failed);
  await vi.advanceTimersByTimeAsync(20_000);
  expect(failed).toHaveBeenCalledOnce();
  resolve();
  await state.sdk;
  await Promise.resolve();
  owner.destroy();
  expect(state.construct).not.toHaveBeenCalled();
  expect(ready).not.toHaveBeenCalled();
});

it("releases a model arriving after cancellation without constructing WebGL", async () => {
  let resolve = () => {};
  state.model = new Promise<void>((done) => { resolve = done; });
  const ready = vi.fn();
  const owner = createAvatarRenderer(host, ready, vi.fn());
  await vi.waitFor(() => expect(state.setup).toHaveBeenCalledOnce());
  owner.destroy();
  resolve();
  await vi.waitFor(() => expect(state.release).toHaveBeenCalledOnce());
  expect(state.construct).not.toHaveBeenCalled();
  expect(ready).not.toHaveBeenCalled();
});

it("releases an existing native model even when the texture promise never settles", async () => {
  state.partial = true;
  state.model = new Promise<void>(() => {});
  const owner = createAvatarRenderer(host, vi.fn(), vi.fn());
  await vi.waitFor(() => expect(state.setup).toHaveBeenCalledOnce());
  owner.destroy();
  await Promise.resolve();
  expect(state.release).toHaveBeenCalledOnce();
  expect(state.construct).not.toHaveBeenCalled();
  owner.destroy();
  expect(state.release).toHaveBeenCalledOnce();
});

it("pauses hidden pages and releases the ticker, renderer, observer and context once", async () => {
  const ready = vi.fn();
  const owner = createAvatarRenderer(host, ready, vi.fn());
  await vi.waitFor(() => expect(ready).toHaveBeenCalledOnce());
  expect(state.resize).toHaveBeenCalledWith(300, 200);
  expect(state.start).toHaveBeenCalledOnce();
  doc.hidden = true; visibility();
  expect(state.stop).toHaveBeenCalledOnce();
  owner.destroy(); owner.destroy();
  expect(state.release).toHaveBeenCalledOnce();
  expect(state.destroyApp).toHaveBeenCalledOnce();
  expect(state.lose).toHaveBeenCalledOnce();
  expect(state.disconnect).toHaveBeenCalledOnce();
});
