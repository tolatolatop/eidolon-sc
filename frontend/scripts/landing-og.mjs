// 落地页的分享卡片（Open Graph / Twitter 卡片的图）：人工运行，成图提交进仓库
// （public/sc-opengraph.jpg，旧作品模式由 layout 显式引用；
// X 没有 twitter:image 时用 og:image）。
//
//   npm run build && BACKEND_URL=http://localhost:8000 npm run start   # 构建版，后端要能给出角色列表
//   node scripts/landing-og.mjs [origin]                                # 默认 http://localhost:3000
//
// 底图不用生图：就是落地页自己第 1 幕的完成态（白光射进棱镜、散成每位偶像的印象色），由页面上同一套
// 着色器画出来，风格和页面一致，角色增减、印象色改了以后重跑一遍就对上。不出现角色形象和任何 logo。
// 加工全在浏览器里做完再截图：
//   1. 视口 1200×630（各平台大图卡片的通用尺寸，1.91:1），DPR 1，完整档；
//   2. 滚到第 1 幕的完成态，等光层淡入、画面停稳；
//   3. 收起页面上的界面（幕名轨、右上角入口、第 1 幕的文字、滚动条）；
//   4. 左下角的暗处排上标题、副标题和非官方声明：文字取自页面上第 0 幕的那几行（文案目录），
//      字体是落地页的子集字体；
//   5. 盖一层暗角（四周压暗，视线落到棱镜上）和一层颗粒（SVG feTurbulence，overlay 叠加，很淡：不能把黑底抬成灰）；
//   6. 截成 JPEG（质量 88）：颗粒让 PNG 很大，聊天软件对预览图的体积有限制。
// 微信、QQ 的链接卡片会把图裁成方形缩略图，中间那块正好是棱镜和刚散开的光。

import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

import { ACT1_SCREENS } from "../src/app/(landing)/model/timeline.ts";

const origin = (process.argv[2] ?? "http://localhost:3000").replace(/\/$/, "");
const frontend = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const SIZE = { width: 1200, height: 630 };

/** 颗粒：一小块分形噪声平铺。 */
const GRAIN =
  "data:image/svg+xml," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240"><filter id="n"><feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="2" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter><rect width="100%" height="100%" filter="url(#n)"/></svg>`,
  );

const CARD_CSS = `
  html { scrollbar-width: none; }
  .lp-rail, .lp-top, .lp-act1-copy, .lp-footer { visibility: hidden !important; }
  .og-card { position: fixed; inset: 0; z-index: 50; pointer-events: none; }
  .og-vignette { position: absolute; inset: 0; background: radial-gradient(120% 110% at 36% 44%, transparent 52%, rgb(0 0 0 / 0.55)); }
  .og-grain { position: absolute; inset: 0; background: url("${GRAIN}"); mix-blend-mode: overlay; opacity: 0.14; }
  .og-text { position: absolute; left: 64px; bottom: 56px; }
  .og-title { margin: 0; font-family: var(--lp-ja); font-weight: 600; font-size: 96px; line-height: 0.95; letter-spacing: -0.02em; font-feature-settings: "palt"; color: #f6f4f8; }
  .og-lede { margin: 22px 0 0; font-family: var(--lp-zh-title); font-weight: 600; font-size: 32px; letter-spacing: 0.08em; color: #dcd9e1; }
  .og-note { margin: 34px 0 0; font-family: var(--lp-zh); font-size: 15px; letter-spacing: 0.06em; color: rgb(238 236 242 / 0.62); }
`;

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: SIZE, deviceScaleFactor: 1 });
  await page.goto(`${origin}/`);
  const tier = await page.evaluate(() => document.documentElement.dataset.lpTier);
  if (tier !== "full") throw new Error(`要在完整档里截图，现在是 ${tier}（无头浏览器的 WebGL 不可用？）`);
  await page.waitForFunction(() => document.querySelector(".lp-root")?.classList.contains("lp-gl-on"), null, { timeout: 20000 });

  // 第 1 幕的完成态。
  await page.evaluate((act1) => {
    const wrap = document.querySelector(".lp-stage-wrap");
    const top = wrap.getBoundingClientRect().top + window.scrollY;
    window.scrollTo(0, top + act1 * window.innerHeight);
  }, ACT1_SCREENS);

  await page.addStyleTag({ content: CARD_CSS });
  await page.evaluate(() => {
    const text = (sel) => document.querySelector(sel).textContent;
    const card = document.createElement("div");
    card.className = "og-card";
    card.innerHTML = `<div class="og-vignette"></div><div class="og-text"><p class="og-title"></p><p class="og-lede"></p><p class="og-note"></p></div><div class="og-grain"></div>`;
    card.querySelector(".og-title").textContent = text("#lp-title");
    card.querySelector(".og-lede").textContent = text(".lp-lede");
    card.querySelector(".og-note").textContent = text(".lp-disclaimer");
    // 放进 .lp-root：落地页的字体变量（--lp-ja 等）定义在它上面。
    document.querySelector(".lp-root").append(card);
  });
  await page.evaluate(() => document.fonts.ready);
  // 等弹簧和淡入走完、画面停稳。
  await page.waitForTimeout(3000);

  const og = path.join(frontend, "public", "sc-opengraph.jpg");
  await page.screenshot({ path: og, type: "jpeg", quality: 88 });
  console.log(`写好了 ${path.relative(frontend, og)}`);
} finally {
  await browser.close();
}
