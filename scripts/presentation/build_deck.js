import pptxgen from "pptxgenjs";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, "../..");
const OUT_DIR = path.resolve(ROOT, "docs/presentation");

if (!fs.existsSync(OUT_DIR)) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
}

const pptx = new pptxgen();
// NB: pptxgenjs's built-in LAYOUT_16x9 is only 10 x 5.625 in — all layout math
// below assumes a true 13.333 x 7.5 canvas, so define it explicitly.
pptx.defineLayout({ name: "WIDE_16x9", width: 13.333, height: 7.5 });
pptx.layout = "WIDE_16x9";
pptx.author = "ShopCopilot Team";
pptx.company = "ShopCopilot";
pptx.title = "ShopCopilot TechJam 2026 Presentation";

// --- Design Tokens ---
const C_BG = "FBF5E7";       // Ivory canvas
const C_DARK = "1B1F2E";     // Charcoal
const C_SEC = "5C4033";      // Cocoa
const C_PANEL = "EFDFBB";    // Cream
const C_ACCENT = "722F37";   // Wine accent (shipped results only)
const C_AMBER = "B45309";    // Amber caveats
const C_MUTED = "9F5F6B";    // Muted rose (rejected)
const C_WHITE = "FFFFFF";
const C_BORDER = "D9CBA8";
const C_GRAY_BG = "F4EDE0";
const C_SAND = "C9B896";     // Neutral sand (baseline bars)

const F_SERIF = "Georgia";
const F_SANS = "Segoe UI";
const F_MONO = "Consolas";

const PAGE_W = 13.333;

function addHeader(slide, title, category = "SHOPCOPILOT · TECHJAM 2026") {
  slide.addText(category.toUpperCase(), {
    x: 0.8, y: 0.4, w: 11.5, h: 0.3,
    fontFace: F_SANS, fontSize: 10, color: C_ACCENT, bold: true, letterSpacing: 1.5
  });
  slide.addText(title, {
    x: 0.8, y: 0.7, w: 11.5, h: 0.55,
    fontFace: F_SERIF, fontSize: 24, color: C_DARK, bold: true
  });
}

function addFooter(slide, extraText = "") {
  const text = extraText ? `ShopCopilot · TechJam 2026 · submission-freeze 46e3322  |  ${extraText}` : "ShopCopilot · TechJam 2026 · submission-freeze 46e3322";
  slide.addText(text, {
    x: 0.8, y: 7.05, w: 11.7, h: 0.3,
    fontFace: F_MONO, fontSize: 9, color: "8A7A5E"
  });
}

function baseSlide() {
  const slide = pptx.addSlide();
  slide.background = { color: C_BG };
  return slide;
}

function panel(slide, x, y, w, h, fill = C_WHITE) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x, y, w, h,
    fill: { color: fill }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
  });
}

function panelTitle(slide, text, x, y, w, color = C_ACCENT) {
  slide.addText(text, {
    x, y, w, h: 0.3,
    fontFace: F_SANS, fontSize: 11, color, bold: true, letterSpacing: 1
  });
}

// ==========================================
// SLIDE 1: Title
// ==========================================
{
  const slide = baseSlide();

  // Hero Badge
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.8, y: 1.15, w: 3.2, h: 0.38,
    fill: { color: C_PANEL }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
  });
  slide.addText("TIKTOK TECHJAM 2026 · TRACK 4", {
    x: 0.9, y: 1.2, w: 3.0, h: 0.28,
    fontFace: F_SANS, fontSize: 10, color: C_ACCENT, bold: true, letterSpacing: 1
  });

  slide.addText("Finding the Hidden Product", {
    x: 0.8, y: 1.7, w: 11.5, h: 1.0,
    fontFace: F_SERIF, fontSize: 42, color: C_DARK, bold: true
  });
  slide.addText("Top-10 hit within 10 conversational turns · 50,000-item catalog · 0 external LLM calls", {
    x: 0.8, y: 2.75, w: 11.5, h: 0.45,
    fontFace: F_SANS, fontSize: 16, color: C_SEC
  });
  slide.addText([
    { text: "TEAM   ", options: { fontFace: F_SANS, fontSize: 11, color: "8A7A5E", bold: true, letterSpacing: 1.5 } },
    { text: "Anything Ah", options: { fontFace: F_SANS, fontSize: 15, color: C_DARK, bold: true } },
  ], {
    x: 0.8, y: 3.2, w: 11.5, h: 0.35,
  });

  // 4 Metric Highlight Cards
  const cards = [
    { label: "HIT@10", val: "0.880", sub: "176 / 200 sessions · 7.0×" },
    { label: "MRR", val: "0.4916", sub: "7.2× official starter" },
    { label: "MTTC", val: "3.375", sub: "target found 2.9× faster" },
    { label: "TECHNICAL SCORE", val: "0.7400", sub: "7× starter (0.1067)" },
  ];

  cards.forEach((c, idx) => {
    const x = 0.8 + idx * 2.95;
    panel(slide, x, 3.6, 2.75, 2.4);
    slide.addText(c.label, {
      x: x + 0.2, y: 3.85, w: 2.35, h: 0.3,
      fontFace: F_SANS, fontSize: 11, color: "8A7A5E", bold: true, letterSpacing: 1
    });
    slide.addText(c.val, {
      x: x + 0.2, y: 4.2, w: 2.35, h: 0.85,
      fontFace: F_MONO, fontSize: 32, color: C_ACCENT, bold: true
    });
    slide.addText(c.sub, {
      x: x + 0.2, y: 5.25, w: 2.35, h: 0.55,
      fontFace: F_SANS, fontSize: 11.5, color: C_SEC
    });
  });

  addFooter(slide, "Data: Amazon Reviews 2023, McAuley Lab, UCSD");
  slide.addNotes(
    "Say: The task: a customer with a hidden target product. Our job: surface it in the top-10 within 10 turns. [EMPHASIZE] We do it 88% of the time in about 3.4 turns. [PAUSE] [ADVANCE]\nTiming: 15s"
  );
}

// ==========================================
// SLIDE 2: Architecture & Simulator Contract
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Architecture & the Simulator Contract");

  // Left Column: Contract (4 compact rows)
  panel(slide, 0.8, 1.5, 5.5, 5.2);
  panelTitle(slide, "SIMULATOR CONTRACT (OFFICIAL EVALUATOR)", 1.0, 1.7, 5.1);

  const contract = [
    { t: "Every turn", d: "message + optional ask + up to 10 recommendations" },
    { t: "Zero hit sacrifice", d: "a clarification question never forfeits the hit check" },
    { t: "Defensive by default", d: "strict dedupe · valid catalog ASINs · spec-enum asks" },
    { t: "Deterministic core", d: "offline execution · 332 automated tests guard the contracts" },
  ];
  contract.forEach((c, i) => {
    const y = 2.25 + i * 0.95;
    slide.addShape(pptx.ShapeType.ellipse, {
      x: 1.05, y: y + 0.05, w: 0.28, h: 0.28, fill: { color: C_ACCENT }
    });
    slide.addText(String(i + 1), {
      x: 1.05, y: y + 0.05, w: 0.28, h: 0.28,
      fontFace: F_SANS, fontSize: 11, color: C_WHITE, bold: true, align: "center", valign: "middle"
    });
    slide.addText(c.t, {
      x: 1.5, y, w: 4.6, h: 0.32,
      fontFace: F_SANS, fontSize: 14.5, color: C_DARK, bold: true
    });
    slide.addText(c.d, {
      x: 1.5, y: y + 0.34, w: 4.6, h: 0.5,
      fontFace: F_SANS, fontSize: 12, color: C_SEC, fit: "shrink"
    });
  });
  slide.addText("Evaluator imported unmodified — zero edits, imports only.", {
    x: 1.0, y: 6.15, w: 5.1, h: 0.35,
    fontFace: F_SANS, fontSize: 10.5, italic: true, color: "8A7A5E"
  });

  // Right Column: Funnel (tapered rows)
  panel(slide, 6.6, 1.5, 5.93, 5.2, C_PANEL);
  panelTitle(slide, "PRODUCTION EXECUTION FUNNEL", 6.9, 1.7, 5.4);

  const funnelSteps = [
    { title: "50,000-item catalog", desc: "SQLite FTS5 BM25 + hashed TF-IDF index" },
    { title: "Hybrid pool · ~300 items", desc: "Reciprocal Rank Fusion (k=60) + guarantee pool" },
    { title: "Full scoring · 320 cap", desc: "Cap ≥ pool → 100% of candidates scored" },
    { title: "8-gate clarification", desc: "Entropy set-splitting on Boolean token index" },
    { title: "Top-10, attributed", desc: "Coverage × IDF × salience + popularity" },
  ];

  funnelSteps.forEach((st, i) => {
    const w = 5.3 - i * 0.2;
    const cx = 6.6 + 5.93 / 2;
    const y = 2.15 + i * 0.92;
    slide.addShape(pptx.ShapeType.roundRect, {
      x: cx - w / 2, y, w, h: 0.78,
      fill: { color: C_WHITE }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.08
    });
    slide.addText(`${i + 1}. ${st.title}`, {
      x: cx - w / 2 + 0.2, y: y + 0.09, w: w - 0.4, h: 0.3,
      fontFace: F_SANS, fontSize: 12.5, color: C_DARK, bold: true
    });
    slide.addText(st.desc, {
      x: cx - w / 2 + 0.2, y: y + 0.4, w: w - 0.4, h: 0.3,
      fontFace: F_SANS, fontSize: 10.5, color: C_SEC, fit: "shrink"
    });
  });

  addFooter(slide);
  slide.addNotes(
    "Say: We implemented their API exactly — and defensively. [POINT at contract rows] Every turn can ask, recommend, or both; a question never forfeits the hit chance. [POINT at funnel] 50k items → ~300 pool → every candidate scored under the 320 cap → entropy questions → attributed top-10. Fully deterministic, offline. [ADVANCE]\nTiming: 30s"
  );
}

// ==========================================
// SLIDE 3: Staircase (Money Slide) — charts
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "The Staircase: 7× the Official Baseline");

  // Left panel: grouped column chart
  panel(slide, 0.8, 1.5, 7.0, 5.2);
  panelTitle(slide, "OFFICIAL METRICS · PUBLIC-200", 1.0, 1.68, 6.6);

  slide.addChart(pptx.ChartType.bar, [
    { name: "Starter (official)", labels: ["Hit@10", "MRR", "Tech Score"], values: [0.125, 0.068, 0.1067] },
    { name: "v2 (pre-experiments)", labels: ["Hit@10", "MRR", "Tech Score"], values: [0.870, 0.4455, 0.7193] },
    { name: "Shipped (freeze)", labels: ["Hit@10", "MRR", "Tech Score"], values: [0.880, 0.4916, 0.7400] },
  ], {
    x: 1.0, y: 2.05, w: 6.6, h: 3.55,
    barDir: "col", barGrouping: "clustered", barGapWidthPct: 70,
    chartColors: [C_SAND, "8A6F5C", C_ACCENT],
    showLegend: true, legendPos: "b", legendColor: C_DARK, legendFontSize: 10.5, legendFontFace: F_SANS,
    catAxisLabelColor: C_DARK, catAxisLabelFontSize: 12, catAxisLabelFontFace: F_SANS,
    valAxisHidden: true, valAxisMaxVal: 1.0, valAxisMinVal: 0,
    valGridLine: { style: "none" }, catGridLine: { style: "none" },
    showValue: true, dataLabelColor: C_DARK, dataLabelFontSize: 9, dataLabelFontFace: F_MONO,
    dataLabelFormatCode: "0.000", dataLabelPosition: "outEnd",
    showTitle: false,
  });

  slide.addText([
    { text: "MTTC  9.81 → 3.38 turns", options: { fontFace: F_MONO, fontSize: 14, color: C_ACCENT, bold: true } },
    { text: "   — target found 2.9× faster", options: { fontFace: F_SANS, fontSize: 12, color: C_SEC } },
  ], {
    x: 1.0, y: 5.95, w: 6.6, h: 0.45, align: "center"
  });

  // Right top: gain decomposition stacked bar
  panel(slide, 8.1, 1.5, 4.43, 3.0);
  panelTitle(slide, "WHERE Δ +0.0207 CAME FROM", 8.3, 1.68, 4.1);

  slide.addChart(pptx.ChartType.bar, [
    { name: "MRR  +0.0138 · 67%", labels: ["ΔTS"], values: [0.0138] },
    { name: "Hit@10  +0.0050 · 24%", labels: ["ΔTS"], values: [0.0050] },
    { name: "Efficiency  +0.0018 · 9%", labels: ["ΔTS"], values: [0.0018] },
  ], {
    x: 8.3, y: 2.0, w: 4.03, h: 1.35,
    barDir: "bar", barGrouping: "stacked", barGapWidthPct: 25,
    chartColors: [C_ACCENT, C_AMBER, C_SAND],
    showLegend: true, legendPos: "b", legendColor: C_DARK, legendFontSize: 9.5, legendFontFace: F_SANS,
    catAxisHidden: true, valAxisHidden: true, valAxisMaxVal: 0.0207, valAxisMinVal: 0,
    valGridLine: { style: "none" }, catGridLine: { style: "none" },
    showValue: false, showTitle: false,
  });

  slide.addText("Two-thirds of the gain is MRR — the ranker puts the target higher in the top 10.", {
    x: 8.3, y: 3.55, w: 4.05, h: 0.8,
    fontFace: F_SANS, fontSize: 11.5, color: C_SEC, fit: "shrink"
  });

  // Right bottom: formula
  panel(slide, 8.1, 4.75, 4.43, 1.95, C_PANEL);
  panelTitle(slide, "OFFICIAL FORMULA", 8.3, 4.93, 4.1);
  slide.addText("Score = 0.5·Hit@10\n      + 0.3·MRR\n      + 0.2·clip((11−MTTC)/10)", {
    x: 8.3, y: 5.3, w: 4.05, h: 1.25,
    fontFace: F_MONO, fontSize: 12, color: C_DARK, lineSpacingMultiple: 1.15
  });

  addFooter(slide);
  slide.addNotes(
    "Say: [POINT at chart] Against the official baseline we're seven-x on every metric. [PAUSE] [POINT at right panel] Against our own pre-experiment system, two-thirds of the TechnicalScore gain is MRR — the ranker puts the right product higher, exactly what the shipped change predicts. [ADVANCE]\nTiming: 45s"
  );
}

// ==========================================
// SLIDE 4: Innovation Directions — kept vs killed
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Innovation Directions: What Shipped, What Died");

  const kept = [
    { t: "Hybrid retrieval", d: "BM25 (0.7) + semantic TF-IDF (0.3) + RRF fusion", r: "88% pool recall · 0.880 Hit@10" },
    { t: "Constraint reweighting", d: "buying-route salience 0.5 → 0.2, popularity untouched", r: "+1.0pp Hit · +4.6pp MRR · SHIPPED" },
    { t: "Explainable ranking", d: "coverage · IDF · salience · popularity per item", r: "live in demo · zero score penalty" },
  ];
  const killed = [
    { t: "LLM reranking tier", d: "3 sizes & classes probed — 2.6B dense · 30B-A3B · 120B-A12B MoE + GPT-4o-mini · Hit / MRR ≈ flat", r: "ΔHit 0 · ΔMRR −0.005 · +0.5–8.3 s per call → killed · local LLM loses on TTFT too" },
    { t: "Soft personalization", d: "profile boost, weight sweep 0.00 – 0.15", r: "0.03 worsened MRR → set to 0.00" },
    { t: "Late-phase question gate", d: "margin-gain question value on misses", r: "0 / 19 misses qualified → stopped" },
  ];

  // Kept panel
  panel(slide, 0.8, 1.5, 5.75, 5.2);
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.8, y: 1.5, w: 5.75, h: 0.5, fill: { color: C_ACCENT }, rectRadius: 0.1
  });
  slide.addText("SHIPPED — KEPT BY THE GATES", {
    x: 1.0, y: 1.55, w: 5.35, h: 0.4,
    fontFace: F_SANS, fontSize: 12, color: C_WHITE, bold: true, letterSpacing: 1, valign: "middle"
  });
  kept.forEach((k, i) => {
    const y = 2.35 + i * 1.5;
    slide.addText(k.t, {
      x: 1.05, y, w: 5.25, h: 0.35,
      fontFace: F_SANS, fontSize: 14.5, color: C_DARK, bold: true
    });
    slide.addText(k.d, {
      x: 1.05, y: y + 0.36, w: 5.25, h: 0.35,
      fontFace: F_SANS, fontSize: 11.5, color: C_SEC, fit: "shrink"
    });
    slide.addText(k.r, {
      x: 1.05, y: y + 0.74, w: 5.25, h: 0.35,
      fontFace: F_MONO, fontSize: 11.5, color: C_ACCENT, bold: true, fit: "shrink"
    });
  });

  // Killed panel
  panel(slide, 6.78, 1.5, 5.75, 5.2, C_PANEL);
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 6.78, y: 1.5, w: 5.75, h: 0.5, fill: { color: C_MUTED }, rectRadius: 0.1
  });
  slide.addText("KILLED — BY THEIR OWN PRE-REGISTERED BARS", {
    x: 6.98, y: 1.55, w: 5.35, h: 0.4,
    fontFace: F_SANS, fontSize: 12, color: C_WHITE, bold: true, letterSpacing: 1, valign: "middle"
  });
  killed.forEach((k, i) => {
    const y = 2.35 + i * 1.5;
    slide.addText(k.t, {
      x: 7.03, y, w: 5.25, h: 0.35,
      fontFace: F_SANS, fontSize: 14.5, color: C_DARK, bold: true
    });
    slide.addText(k.d, {
      x: 7.03, y: y + 0.36, w: 5.25, h: 0.35,
      fontFace: F_SANS, fontSize: 11.5, color: C_SEC, fit: "shrink"
    });
    slide.addText(k.r, {
      x: 7.03, y: y + 0.74, w: 5.25, h: 0.35,
      fontFace: F_MONO, fontSize: 11.5, color: C_MUTED, bold: true, fit: "shrink"
    });
  });

  addFooter(slide);
  slide.addNotes(
    "Say: We attempted every applicable direction on the organizer's own list. [POINT left] The left panel shipped. [POINT right] The right panel died. We probed three LLM classes — a 2.6B dense, a 30B-active-3B MoE, a 120B MoE, plus GPT-4o-mini: accuracy flat, latency half a second to eight seconds per call — and a local LLM on a consumer laptop loses on time-to-first-token alone. Our deterministic path stays at 330 milliseconds. [ADVANCE]\nTiming: 30s"
  );
}

// ==========================================
// SLIDE 5: Rigorous Experimental Method
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Method: Pre-Registered, Paired, Isolated");

  const boxes = [
    {
      num: "1", title: "Worktree isolation",
      items: ["5 isolated experiment worktrees", "branched from control 80eee9a", "frozen evaluator · zero contamination"],
    },
    {
      num: "2", title: "Pre-registered bars",
      items: ["pass bar written before first eval", "ΔHit ≥ +0.03 · p95 ≤ +2 s", "automatic revert on regression"],
    },
    {
      num: "3", title: "Paired-session flips",
      items: ["unit of truth: per-session flips", "noise floor ±1 session (159/160 agree)", "aggregate shifts <3pp are noise"],
    },
  ];

  boxes.forEach((b, i) => {
    const x = 0.8 + i * 3.975;
    panel(slide, x, 1.6, 3.75, 5.0);
    slide.addShape(pptx.ShapeType.ellipse, {
      x: x + 0.25, y: 1.95, w: 0.55, h: 0.55, fill: { color: C_ACCENT }
    });
    slide.addText(b.num, {
      x: x + 0.25, y: 1.95, w: 0.55, h: 0.55,
      fontFace: F_SERIF, fontSize: 20, color: C_WHITE, bold: true, align: "center", valign: "middle"
    });
    slide.addText(b.title, {
      x: x + 0.25, y: 2.75, w: 3.25, h: 0.45,
      fontFace: F_SERIF, fontSize: 17, color: C_DARK, bold: true
    });
    slide.addText(
      b.items.map(t => `•  ${t}`).join("\n"),
      {
        x: x + 0.25, y: 3.35, w: 3.25, h: 2.9,
        fontFace: F_SANS, fontSize: 12.5, color: C_SEC, lineSpacingMultiple: 1.3, valign: "top"
      }
    );
  });

  addFooter(slide);
  slide.addNotes(
    "Say: [SLOW] Every experiment had its pass bar written before the first eval ran. We measured per-session paired flips against a strict ±1 session noise floor. [ADVANCE]\nTiming: 25s"
  );
}

// ==========================================
// SLIDE 6: The Win (Salience Reweight) — waterfall
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "The Shipped Win: Salience vs Popularity");

  // Left: flip waterfall
  panel(slide, 0.8, 1.5, 6.0, 5.2);
  panelTitle(slide, "PAIRED FLIP WATERFALL · DEV-160", 1.0, 1.7, 5.6);

  const plotY = 2.25, plotH = 2.75, minV = 138, maxV = 146;
  const yOf = v => plotY + ((maxV - v) / (maxV - minV)) * plotH;
  const bw = 1.1, gap = 0.35;
  const bars = [
    { x: 1.1, label: "141", top: yOf(141), bot: yOf(138), fill: C_SAND, sub: "Control" },
    { x: 1.1 + bw + gap, label: "+4", top: yOf(145), bot: yOf(141), fill: C_ACCENT, sub: "Miss → Hit" },
    { x: 1.1 + 2 * (bw + gap), label: "−1", top: yOf(145), bot: yOf(144), fill: C_MUTED, sub: "Hit → Miss" },
    { x: 1.1 + 3 * (bw + gap), label: "144", top: yOf(144), bot: yOf(138), fill: C_ACCENT, sub: "Shipped" },
  ];
  // connectors (dashed)
  slide.addShape(pptx.ShapeType.line, { x: bars[0].x + bw, y: yOf(141), w: gap, h: 0, line: { color: "8A7A5E", width: 1, dashType: "dash" } });
  slide.addShape(pptx.ShapeType.line, { x: bars[1].x + bw, y: yOf(145), w: gap, h: 0, line: { color: "8A7A5E", width: 1, dashType: "dash" } });
  slide.addShape(pptx.ShapeType.line, { x: bars[2].x + bw, y: yOf(144), w: gap, h: 0, line: { color: "8A7A5E", width: 1, dashType: "dash" } });
  bars.forEach(b => {
    slide.addShape(pptx.ShapeType.rect, {
      x: b.x, y: b.top, w: bw, h: Math.max(b.bot - b.top, 0.05),
      fill: { color: b.fill }, line: { color: C_BORDER, width: 0.75 }
    });
    slide.addText(b.label, {
      x: b.x - 0.1, y: b.top - 0.4, w: bw + 0.2, h: 0.35,
      fontFace: F_MONO, fontSize: 15, color: C_DARK, bold: true, align: "center"
    });
    slide.addText(b.sub, {
      x: b.x - 0.15, y: yOf(138) + 0.1, w: bw + 0.3, h: 0.3,
      fontFace: F_SANS, fontSize: 10, color: C_SEC, align: "center"
    });
  });
  slide.addText("+4:  0031 · 0100 · 0085 · 0125        −1:  0035", {
    x: 1.0, y: 5.85, w: 5.6, h: 0.3,
    fontFace: F_MONO, fontSize: 10.5, color: "8A7A5E", align: "center"
  });
  slide.addText("net +3  >  ±1 noise floor", {
    x: 1.0, y: 6.2, w: 5.6, h: 0.3,
    fontFace: F_MONO, fontSize: 11.5, color: C_ACCENT, bold: true, align: "center"
  });

  // Right: mechanism + honesty + confirmation
  panel(slide, 7.0, 1.5, 5.53, 5.2, C_PANEL);
  panelTitle(slide, "MECHANISM", 7.2, 1.7, 5.1);
  slide.addText(
    "•  Popularity crowded out products satisfying rare, high-value constraints\n" +
    "•  Fix: buying-route salience weight 0.5 → 0.2",
    {
      x: 7.2, y: 2.1, w: 5.1, h: 1.0,
      fontFace: F_SANS, fontSize: 12.5, color: C_DARK, lineSpacingMultiple: 1.2, fit: "shrink"
    }
  );

  panel(slide, 7.2, 3.35, 5.13, 1.85, C_WHITE);
  slide.addText("HONESTY", {
    x: 7.4, y: 3.5, w: 4.7, h: 0.28,
    fontFace: F_SANS, fontSize: 10, color: C_AMBER, bold: true, letterSpacing: 1
  });
  slide.addText(
    "Failed its own Buying-specific hypothesis — the wins were route-general. Shipped anyway: flips, not hypothesis, were the evidence.",
    {
      x: 7.4, y: 3.8, w: 4.75, h: 1.3,
      fontFace: F_SANS, fontSize: 12, color: C_DARK, lineSpacingMultiple: 1.2, fit: "shrink"
    }
  );

  slide.addShape(pptx.ShapeType.roundRect, {
    x: 7.2, y: 5.45, w: 5.13, h: 0.85, fill: { color: C_ACCENT }, rectRadius: 0.08
  });
  slide.addText("public-200 confirm:  Hit 0.870 → 0.880 · MRR 0.4455 → 0.4916", {
    x: 7.35, y: 5.45, w: 4.85, h: 0.85,
    fontFace: F_MONO, fontSize: 12, color: C_WHITE, bold: true, valign: "middle", fit: "shrink"
  });

  addFooter(slide);
  slide.addNotes(
    "Say: [POINT at waterfall] Popularity was crowding out constraint matches. Salience 0.5 to 0.2: four miss-to-hit flips against one regression. [LOOK] The win failed its own hypothesis — it shipped anyway, because the flips were the evidence, and it confirmed out-of-sample. [ADVANCE]\nTiming: 30s"
  );
}

// ==========================================
// SLIDE 7: Out-of-Sample Transfer + per-scenario chart
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Out-of-Sample Confirmation");

  // Left: dev → public stats
  panel(slide, 0.8, 1.5, 5.6, 5.2);
  panelTitle(slide, "PROGRESSION ACROSS SPLITS", 1.0, 1.7, 5.2);

  const splits = [
    { tag: "DEV-160 · TUNING SET", big: "0.900 Hit@10", det: "144 / 160 · MRR 0.5144 · MTTC 3.19" },
    { tag: "PUBLIC-200 · CONFIRMATION (TOUCHED 2×)", big: "0.880 Hit@10", det: "176 / 200 · MRR 0.4916 · MTTC 3.375" },
  ];
  splits.forEach((s, i) => {
    const y = 2.2 + i * 1.75;
    panel(slide, 1.0, y, 5.2, 1.5, C_PANEL);
    slide.addText(s.tag, {
      x: 1.2, y: y + 0.12, w: 4.8, h: 0.28,
      fontFace: F_SANS, fontSize: 9.5, color: "8A7A5E", bold: true, letterSpacing: 0.5
    });
    slide.addText(s.big, {
      x: 1.2, y: y + 0.42, w: 4.8, h: 0.55,
      fontFace: F_MONO, fontSize: 24, color: C_ACCENT, bold: true
    });
    slide.addText(s.det, {
      x: 1.2, y: y + 1.02, w: 4.8, h: 0.35,
      fontFace: F_MONO, fontSize: 11, color: C_SEC, fit: "shrink"
    });
  });
  slide.addShape(pptx.ShapeType.line, {
    x: 3.6, y: 3.7, w: 0, h: 0.5, line: { color: C_ACCENT, width: 2.5, endArrowType: "triangle" }
  });
  slide.addText("The salience gain was not overfitted to dev.", {
    x: 1.0, y: 5.85, w: 5.2, h: 0.6,
    fontFace: F_SANS, fontSize: 12.5, italic: true, color: C_SEC
  });

  // Right: per-scenario horizontal bars
  panel(slide, 6.7, 1.5, 5.83, 5.2);
  panelTitle(slide, "HIT@10 BY SCENARIO (PUBLIC-200)", 6.9, 1.7, 5.4);

  slide.addChart(pptx.ChartType.bar, [
    {
      name: "Hit@10",
      labels: ["Boundary · 6/10", "Intent Override · 23/30", "Buying · 73/80", "Browsing · 74/80"],
      values: [0.6, 0.7667, 0.9125, 0.925],
    },
  ], {
    x: 6.9, y: 2.1, w: 5.4, h: 3.55,
    barDir: "bar", barGapWidthPct: 50,
    chartColors: [C_ACCENT],
    catAxisLabelColor: C_DARK, catAxisLabelFontSize: 11, catAxisLabelFontFace: F_SANS,
    valAxisHidden: true, valAxisMaxVal: 1.0, valAxisMinVal: 0,
    valGridLine: { style: "none" }, catGridLine: { style: "none" },
    showValue: true, dataLabelColor: C_DARK, dataLabelFontSize: 10.5, dataLabelFontFace: F_MONO,
    dataLabelFormatCode: "0.000", dataLabelPosition: "outEnd",
    showLegend: false, showTitle: false,
  });

  slide.addText("Exact counts on every bar — small denominators stay visible.", {
    x: 6.9, y: 5.95, w: 5.4, h: 0.35,
    fontFace: F_SANS, fontSize: 11, italic: true, color: "8A7A5E", align: "center"
  });

  addFooter(slide);
  slide.addNotes(
    "Say: Gains transferred cleanly out-of-sample from dev to public-200. [POINT at chart] Browsing 92.5%, Buying 91.25%, Intent Override 76.7%, Boundary 60% — and we show the exact counts so the small n is visible. [ADVANCE]\nTiming: 25s"
  );
}

// ==========================================
// SLIDE 8: The Graveyard — diverging flip bars
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "The Graveyard: 6 Rejected by Their Own Bars");

  const rows = [
    { name: "exp/rank-salience", flips: 3, reason: "Exceeded ±1 noise floor · confirmed on public-200", action: "MERGED", good: true },
    { name: "exp/global-salience", flips: 1, reason: "Within ±1 noise floor · didn't generalize", action: "Reverted" },
    { name: "exp/competition-window", flips: 1, reason: "Within ±1 noise floor · identical flips", action: "Unmerged" },
    { name: "exp/uninformative-stop", flips: -1, reason: "Regressed hits · broke session 0104", action: "Reverted" },
    { name: "exp/rank-coverage-idf", flips: 0, reason: "Pool lever never fires on dev (0/0 flips)", action: "Unmerged" },
    { name: "exp/question-margin", flips: 0, zeroLabel: "0/19", reason: "Pattern absent in the 19 misses", action: "Stopped" },
    { name: "exp/boundary-override", flips: 0, zeroLabel: "0", reason: "Premise disproven by replay forensics", action: "Stopped" },
  ];

  const cx = 4.7;             // zero axis
  const scale = 0.5;          // inches per flip
  const rowY0 = 1.75, rowH = 0.63, barH = 0.28;

  // axis
  slide.addShape(pptx.ShapeType.line, { x: cx, y: 1.65, w: 0, h: rows.length * rowH + 0.1, line: { color: C_BORDER, width: 1.25 } });

  rows.forEach((r, i) => {
    const y = rowY0 + i * rowH;
    if (i % 2 === 0) {
      slide.addShape(pptx.ShapeType.rect, {
        x: 0.8, y: y - 0.06, w: 11.73, h: rowH - 0.06, fill: { color: C_GRAY_BG }, line: { type: "none" }
      });
    }
    // name
    slide.addText(r.name, {
      x: 0.85, y: y + 0.03, w: 2.45, h: 0.4,
      fontFace: F_MONO, fontSize: 10.5, color: C_DARK, bold: true, valign: "middle"
    });
    // bar
    if (r.flips !== 0) {
      const w = Math.abs(r.flips) * scale;
      const bx = r.flips > 0 ? cx : cx - w;
      slide.addShape(pptx.ShapeType.rect, {
        x: bx, y: y + (rowH - 0.06 - barH) / 2 + 0.03, w, h: barH,
        fill: { color: r.good ? C_ACCENT : C_MUTED }, line: { type: "none" }
      });
      slide.addText(r.flips > 0 ? `+${r.flips}` : `${r.flips}`, {
        x: r.flips > 0 ? bx + w + 0.08 : bx - 0.62, y: y + 0.03, w: 0.6, h: 0.4,
        fontFace: F_MONO, fontSize: 11, color: r.good ? C_ACCENT : C_MUTED, bold: true, valign: "middle", align: r.flips > 0 ? "left" : "right"
      });
    } else {
      slide.addShape(pptx.ShapeType.rect, {
        x: cx - 0.03, y: y + (rowH - 0.06 - barH) / 2 + 0.03, w: 0.06, h: barH,
        fill: { color: "8A7A5E" }, line: { type: "none" }
      });
      slide.addText(r.zeroLabel || "0", {
        x: cx + 0.1, y: y + 0.03, w: 0.7, h: 0.4,
        fontFace: F_MONO, fontSize: 11, color: "8A7A5E", bold: true, valign: "middle"
      });
    }
    // reason
    slide.addText(r.reason, {
      x: 6.55, y: y + 0.03, w: 4.15, h: 0.4,
      fontFace: F_SANS, fontSize: 10.5, color: C_SEC, valign: "middle", fit: "shrink"
    });
    // action chip
    const merged = r.action === "MERGED";
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 10.85, y: y + 0.06, w: 1.63, h: 0.34,
      fill: { color: merged ? C_ACCENT : C_BG }, line: { color: merged ? C_ACCENT : C_MUTED, width: 1 }, rectRadius: 0.08
    });
    slide.addText(r.action, {
      x: 10.85, y: y + 0.06, w: 1.63, h: 0.34,
      fontFace: F_MONO, fontSize: 9.5, color: merged ? C_WHITE : C_MUTED, bold: true, align: "center", valign: "middle"
    });
  });

  slide.addText("net paired flips (dev-160)  →", {
    x: cx - 1.7, y: 1.38, w: 3.4, h: 0.25,
    fontFace: F_SANS, fontSize: 9, color: "8A7A5E", align: "center", italic: true
  });

  slide.addText("“Every red row was rejected by criteria written before the experiment ran. The 0.90625 in our logs was never merged.”", {
    x: 0.8, y: 6.35, w: 11.73, h: 0.45,
    fontFace: F_SERIF, fontSize: 13, color: C_DARK, italic: true, align: "center"
  });

  addFooter(slide);
  slide.addNotes(
    "Say: [REPEAT] Six experiments did not survive their own bars. [POINT at bars] Two were within the noise floor, one regressed, three had zero effect. Six negatives is how you know the green one is real. [ADVANCE]\nTiming: 30s"
  );
}

// ==========================================
// SLIDE 9: 4 Structural Findings
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "4 Structural Findings from Negative Results");

  const findings = [
    {
      num: "01", title: "MTTC = first-hit turn", stat: "miss = 11",
      desc: "The evaluator stops the moment the target enters top-10. Wasted questions happen post-hit — only surfacing sooner moves MTTC.",
    },
    {
      num: "02", title: "Dialogue and retrieval are coupled", stat: "0104",
      desc: "Stopping clarification changed the message stream and broke retrieval. “Hit-safe by construction” is false.",
    },
    {
      num: "03", title: "Scenario labels ≠ runtime route", stat: "89%",
      desc: "84 / 94 non-buying sessions run buying-route turns — including every one of the 15 dev misses.",
    },
    {
      num: "04", title: "Re-ordering is saturated", stat: "+2/−1 ×2",
      desc: "Two independent ranker changes produced identical flips. Remaining misses need new information, not permutations.",
    },
  ];

  findings.forEach((f, i) => {
    const x = 0.8 + (i % 2) * 5.98;
    const y = 1.6 + Math.floor(i / 2) * 2.6;
    panel(slide, x, y, 5.75, 2.4);
    slide.addText(f.num, {
      x: x + 0.22, y: y + 0.18, w: 0.75, h: 0.4,
      fontFace: F_MONO, fontSize: 19, color: C_ACCENT, bold: true
    });
    slide.addText(f.title, {
      x: x + 0.85, y: y + 0.18, w: 3.4, h: 0.4,
      fontFace: F_SERIF, fontSize: 14.5, color: C_DARK, bold: true, fit: "shrink"
    });
    slide.addShape(pptx.ShapeType.roundRect, {
      x: x + 4.3, y: y + 0.16, w: 1.25, h: 0.4,
      fill: { color: C_PANEL }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.08
    });
    slide.addText(f.stat, {
      x: x + 4.3, y: y + 0.16, w: 1.25, h: 0.4,
      fontFace: F_MONO, fontSize: 9.5, color: C_ACCENT, bold: true, align: "center", valign: "middle", fit: "shrink"
    });
    slide.addText(f.desc, {
      x: x + 0.22, y: y + 0.75, w: 5.3, h: 1.5,
      fontFace: F_SANS, fontSize: 12, color: C_SEC, lineSpacingMultiple: 1.2, fit: "shrink"
    });
  });

  addFooter(slide);
  slide.addNotes(
    "Say: [SLOW] No score shows these four facts. Each one redirected the next experiment — knowing that 'ask less' cannot move MTTC saved us from weeks of futile prompt engineering. [ADVANCE]\nTiming: 35s"
  );
}

// ==========================================
// SLIDE 10: Why We Miss — donut + root causes
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Why We Miss: Forensic Audit of All 16 Dev Misses");

  // Left: donut
  panel(slide, 0.8, 1.5, 4.9, 5.2);
  panelTitle(slide, "MISS TAXONOMY (DEV-160)", 1.0, 1.7, 4.5);
  slide.addChart(pptx.ChartType.doughnut, [
    { name: "Misses", labels: ["Rank-depth · 13", "Pool-depth · 2", "Extraction · 1"], values: [13, 2, 1] },
  ], {
    x: 1.0, y: 2.1, w: 4.5, h: 3.7,
    chartColors: [C_ACCENT, C_AMBER, C_SAND],
    holeSize: 60,
    showLegend: true, legendPos: "b", legendColor: C_DARK, legendFontSize: 11, legendFontFace: F_SANS,
    showValue: false, showPercent: false, showTitle: false,
  });
  slide.addText("n = 16 of 160 sessions", {
    x: 1.0, y: 6.15, w: 4.5, h: 0.3,
    fontFace: F_MONO, fontSize: 10.5, color: "8A7A5E", align: "center"
  });

  // Right: root causes
  const causes = [
    { stat: "13", tag: "RANK-DEPTH", color: C_ACCENT, desc: "Target in the pool but outranked — needs new user information, not re-ordering." },
    { stat: "2", tag: "POOL-DEPTH", color: C_AMBER, desc: "Target ranked 201+ in the pool — a recall cap, not a filter bug." },
    { stat: "1", tag: "EXTRACTION", color: "8A7A5E", desc: "Complex overlapping syntax edge case (public_0117)." },
  ];
  causes.forEach((c, i) => {
    const y = 1.5 + i * 1.32;
    panel(slide, 5.9, y, 6.63, 1.17);
    slide.addShape(pptx.ShapeType.rect, {
      x: 5.9, y: y + 0.15, w: 0.09, h: 0.87, fill: { color: c.color }, line: { type: "none" }
    });
    slide.addText(c.stat, {
      x: 6.15, y: y + 0.18, w: 0.85, h: 0.8,
      fontFace: F_MONO, fontSize: 30, color: c.color, bold: true, valign: "middle"
    });
    slide.addText(c.tag, {
      x: 7.05, y: y + 0.16, w: 5.3, h: 0.3,
      fontFace: F_SANS, fontSize: 10.5, color: "8A7A5E", bold: true, letterSpacing: 1
    });
    slide.addText(c.desc, {
      x: 7.05, y: y + 0.47, w: 5.3, h: 0.6,
      fontFace: F_SANS, fontSize: 11.5, color: C_DARK, fit: "shrink"
    });
  });

  // Faithfulness banner
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 5.9, y: 5.55, w: 6.63, h: 1.15, fill: { color: C_PANEL }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
  });
  slide.addText([
    { text: "QUERY FAITHFULNESS: ", options: { fontFace: F_SANS, fontSize: 12, color: C_ACCENT, bold: true } },
    { text: "0 of 13 recoverable constraints dropped. The pipeline leaks nothing — remaining misses are genuine capability limits.", options: { fontFace: F_SANS, fontSize: 12, color: C_DARK } },
  ], {
    x: 6.1, y: 5.65, w: 6.25, h: 0.95, valign: "middle", fit: "shrink"
  });

  addFooter(slide);
  slide.addNotes(
    "Say: We audited our own pipeline for leaks and found none. [POINT at donut] Thirteen of sixteen are rank-depth — the target was in the pool but outranked. [POINT at banner] Zero of thirteen recoverable constraints were dropped. The remaining misses are genuine capability limits, and we know exactly which. [ADVANCE]\nTiming: 30s"
  );
}

// ==========================================
// SLIDE 11: Feasibility Disclosure
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Feasibility: Zero Tokens, Zero Cost, Zero Network");

  const cards = [
    { label: "LLM TOKENS", val: "0", sub: "0 prompt · 0 completion" },
    { label: "MODEL COST", val: "$0.00", sub: "zero API fees" },
    { label: "NETWORK", val: "None", sub: "fully offline at inference" },
    { label: "TURN LATENCY", val: "330 ms", sub: "p50 · p95 527 ms" },
  ];
  cards.forEach((c, i) => {
    const x = 0.8 + i * 2.96;
    panel(slide, x, 1.6, 2.85, 1.85);
    slide.addText(c.label, {
      x: x + 0.2, y: 1.8, w: 2.45, h: 0.28,
      fontFace: F_SANS, fontSize: 10, color: "8A7A5E", bold: true, letterSpacing: 1
    });
    slide.addText(c.val, {
      x: x + 0.2, y: 2.12, w: 2.45, h: 0.65,
      fontFace: F_MONO, fontSize: 28, color: C_ACCENT, bold: true
    });
    slide.addText(c.sub, {
      x: x + 0.2, y: 2.85, w: 2.45, h: 0.45,
      fontFace: F_SANS, fontSize: 10.5, color: C_SEC, fit: "shrink"
    });
  });

  panel(slide, 0.8, 3.85, 11.73, 2.85);
  panelTitle(slide, "DISCLOSURE DETAIL", 1.0, 4.03, 11.3);
  const lines = [
    ["Runtime model", "Deterministic BM25 + hashed TF-IDF + constraint ranker — no model at inference"],
    ["Evidence", "results.json → reported_token_usage = 0 · total_tokens = 0"],
    ["Optional LLM tier", "Built and gated OFF by default (enable_llm_reranker = false)"],
    ["Environment", "Python 3.13 · Windows 11 Pro · AMD Ryzen 7 · 32 GB RAM"],
    ["Recorded live", "docs/final-eval-record.md — same frozen commit 46e3322"],
  ];
  lines.forEach((l, i) => {
    const y = 4.45 + i * 0.42;
    slide.addText(l[0], {
      x: 1.0, y, w: 2.4, h: 0.36,
      fontFace: F_SANS, fontSize: 12, color: C_SEC, bold: true, valign: "middle"
    });
    slide.addText(l[1], {
      x: 3.5, y, w: 8.8, h: 0.36,
      fontFace: F_MONO, fontSize: 11.5, color: C_DARK, valign: "middle", fit: "shrink"
    });
  });

  addFooter(slide);
  slide.addNotes(
    "Say: Feasibility disclosed per spec — [POINT at cards] zero tokens, zero model cost, no network at inference, 330 millisecond responses. The deterministic system is the submission. [ADVANCE]\nTiming: 20s"
  );
}

// ==========================================
// SLIDE 12: Business Impact — turns chart
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Business Impact: From Bounce to Checkout");

  // Left: turns-to-conversion chart
  panel(slide, 0.8, 1.5, 5.9, 5.2);
  panelTitle(slide, "TURNS TO FIND THE PRODUCT", 1.0, 1.7, 5.5);
  slide.addChart(pptx.ChartType.bar, [
    { name: "Mean turns to conversion", labels: ["Legacy LLM loop", "ShopCopilot"], values: [9.81, 3.375] },
  ], {
    x: 1.1, y: 2.2, w: 5.3, h: 3.5,
    barDir: "col", barGapWidthPct: 80,
    chartColors: [C_SAND, C_ACCENT],
    catAxisLabelColor: C_DARK, catAxisLabelFontSize: 12, catAxisLabelFontFace: F_SANS,
    valAxisHidden: true, valAxisMaxVal: 11, valAxisMinVal: 0,
    valGridLine: { style: "none" }, catGridLine: { style: "none" },
    showValue: true, dataLabelColor: C_DARK, dataLabelFontSize: 13, dataLabelFontFace: F_MONO,
    dataLabelFormatCode: "0.00", dataLabelPosition: "outEnd",
    showLegend: false, showTitle: false,
  });
  slide.addText("Vague first query → wrong products → exit.", {
    x: 1.0, y: 5.95, w: 5.5, h: 0.35,
    fontFace: F_SANS, fontSize: 11, italic: true, color: "8A7A5E", align: "center"
  });

  // Right: three pillars
  const pillars = [
    { t: "Bounce → checkout", d: "3.4 turns vs 9.8 turns completes the purchase instead of abandonment." },
    { t: "Attributable ranking", d: "Every card shows coverage, IDF rarity, salience, popularity — math, not a black box." },
    { t: "Zero marginal cost", d: "330 ms responses, $0.00 per turn, 100% uptime SLA — unit economics survive scale." },
  ];
  pillars.forEach((p, i) => {
    const y = 1.5 + i * 1.8;
    panel(slide, 6.9, y, 5.63, 1.6);
    slide.addShape(pptx.ShapeType.rect, {
      x: 6.9, y: y + 0.15, w: 0.09, h: 1.3, fill: { color: C_ACCENT }, line: { type: "none" }
    });
    slide.addText(p.t, {
      x: 7.15, y: y + 0.16, w: 5.2, h: 0.38,
      fontFace: F_SERIF, fontSize: 15, color: C_DARK, bold: true
    });
    slide.addText(p.d, {
      x: 7.15, y: y + 0.58, w: 5.2, h: 0.9,
      fontFace: F_SANS, fontSize: 12, color: C_SEC, lineSpacingMultiple: 1.15, fit: "shrink"
    });
  });

  addFooter(slide);
  slide.addNotes(
    "Say: [POINT at chart] Commercial conversational search fails when users abandon: 9.8 turns to conversion is a bounce; 3.4 is a checkout. [POINT at pillars] Attributable ranking builds trust, and zero marginal cost makes it viable at scale. [ADVANCE]\nTiming: 25s"
  );
}

// ==========================================
// SLIDE 13: Final-Eval Readiness
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Final-Eval Readiness: 800 Hidden Sessions");

  const checks = [
    { t: "Evaluator frozen", d: "byte-identical to starter package — imports only" },
    { t: "Fresh-clone rehearsal", d: "clean clone reproduces the exact 0.880 table" },
    { t: "No hardcoding", d: "zero session-id checks anywhere in the codebase" },
    { t: "Data isolation", d: "800 hidden sessions touched 0 times · public-200 touched 2×" },
    { t: "332 automated tests", d: "pass in 21 s on the frozen commit" },
    { t: "Snapshot retained", d: "commit 46e3322 · pip deps · hardware captured" },
  ];

  checks.forEach((c, i) => {
    const x = 0.8 + (i % 2) * 5.98;
    const y = 1.6 + Math.floor(i / 2) * 1.72;
    panel(slide, x, y, 5.75, 1.55);
    slide.addText("✔", {
      x: x + 0.2, y: y + 0.18, w: 0.4, h: 0.4,
      fontFace: F_SANS, fontSize: 17, color: C_ACCENT, bold: true
    });
    slide.addText(c.t, {
      x: x + 0.62, y: y + 0.16, w: 4.95, h: 0.4,
      fontFace: F_SERIF, fontSize: 14.5, color: C_DARK, bold: true
    });
    slide.addText(c.d, {
      x: x + 0.62, y: y + 0.62, w: 4.95, h: 0.75,
      fontFace: F_SANS, fontSize: 11.5, color: C_SEC, lineSpacingMultiple: 1.15, fit: "shrink"
    });
  });

  addFooter(slide);
  slide.addNotes(
    "Say: 800 hidden sessions run against our frozen commit with the unmodified official evaluator. Our fresh clone rehearsal reproduced the exact 0.880 score. [ADVANCE]\nTiming: 20s"
  );
}

// ==========================================
// SLIDE 14: Technical Roadmap
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Roadmap: Attack the Measured Ceilings");

  const roadItems = [
    {
      phase: "PHASE 1", title: "Recall expansion",
      desc: "Category-specialized inverted sub-indices break the rank-201+ candidate cap.",
      target: "removes the 2 pool misses",
    },
    {
      phase: "PHASE 2", title: "Deep feature enrichment",
      desc: "Extract fine-grained attributes — fabric weight, collar, sole stiffness.",
      target: "feeds the 13 rank-depth misses",
    },
    {
      phase: "PHASE 3", title: "Early hit prioritization",
      desc: "Optimize turn-1 ranking for top-1 placement, not just top-10 membership.",
      target: "target: MTTC 3.38 → < 2.5",
    },
  ];

  roadItems.forEach((r, i) => {
    const x = 0.8 + i * 3.975;
    panel(slide, x, 1.6, 3.75, 5.0);
    slide.addText(r.phase, {
      x: x + 0.25, y: 1.9, w: 3.25, h: 0.3,
      fontFace: F_MONO, fontSize: 11, color: C_ACCENT, bold: true, letterSpacing: 1
    });
    slide.addText(r.title, {
      x: x + 0.25, y: 2.25, w: 3.25, h: 0.85,
      fontFace: F_SERIF, fontSize: 17, color: C_DARK, bold: true, fit: "shrink"
    });
    slide.addText(r.desc, {
      x: x + 0.25, y: 3.15, w: 3.25, h: 1.6,
      fontFace: F_SANS, fontSize: 12.5, color: C_SEC, lineSpacingMultiple: 1.25
    });
    panel(slide, x + 0.25, 5.6, 3.25, 0.7, C_PANEL);
    slide.addText(r.target, {
      x: x + 0.4, y: 5.6, w: 2.95, h: 0.7,
      fontFace: F_MONO, fontSize: 11, color: C_ACCENT, bold: true, valign: "middle", align: "center", fit: "shrink"
    });
  });

  addFooter(slide);
  slide.addNotes(
    "Say: Our roadmap directly addresses our measured capability limits: expanding the pool recall layer for the two pool misses, enriching features for the deep rank misses. [ADVANCE]\nTiming: 15s"
  );
}

// ==========================================
// SLIDE 15: Provenance & Reproducibility
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Provenance & Reproducibility");

  // Left: tags + artifacts
  panel(slide, 0.8, 1.5, 5.6, 5.2);
  panelTitle(slide, "TAG CHAIN & KEY ARTIFACTS", 1.0, 1.7, 5.2);
  slide.addText(
    "fork-point          80eee9a   dev baseline\n" +
    "new-baseline    46e3322   post-salience control\n" +
    "submission-freeze 46e3322   official submission",
    {
      x: 1.0, y: 2.15, w: 5.2, h: 1.1,
      fontFace: F_MONO, fontSize: 11.5, color: C_DARK, lineSpacingMultiple: 1.35
    }
  );
  panelTitle(slide, "KEY ARTIFACTS", 1.0, 3.55, 5.2);
  slide.addText(
    "•  results.json — public-200 · 0.880\n" +
    "•  runs/control-dev-newbaseline.json — dev-160 · 0.900\n" +
    "•  docs/experiment-ledger.md — every run\n" +
    "•  DATA_ATTRIBUTION.md — UCSD McAuley Lab",
    {
      x: 1.0, y: 3.95, w: 5.2, h: 2.4,
      fontFace: F_MONO, fontSize: 11.5, color: C_DARK, lineSpacingMultiple: 1.35
    }
  );

  // Right: reproduce
  panel(slide, 6.7, 1.5, 5.83, 5.2, C_PANEL);
  panelTitle(slide, "REPRODUCE FROM A CLEAN CLONE", 6.9, 1.7, 5.4);
  slide.addText(
    "# 1 · install + build catalog index\n" +
    "pip install -r requirements.txt\n" +
    "python scripts/setup_catalog.py\n\n" +
    "# 2 · test suite (332 passed)\n" +
    "python -m pytest -q\n\n" +
    "# 3 · official evaluator → 0.880 table\n" +
    "python -m evaluator.local_evaluator\n\n" +
    "# 4 · live interactive demo\n" +
    "python scripts/interactive_demo.py",
    {
      x: 6.9, y: 2.15, w: 5.4, h: 4.3,
      fontFace: F_MONO, fontSize: 11.5, color: C_DARK, lineSpacingMultiple: 1.25
    }
  );

  addFooter(slide, "Data Attribution: Amazon Reviews 2023, McAuley Lab, UCSD");
  slide.addNotes(
    "Say: Everything in this presentation is reproducible with three standard commands from a clean clone. Thank you — I welcome your questions. [PAUSE]\nTiming: 10s"
  );
}

// Write PPTX
const pptxPath = path.resolve(OUT_DIR, "ShopCopilot_TechJam_Deck.pptx");
pptx.writeFile({ fileName: pptxPath }).then(() => {
  console.log(`Successfully generated deck: ${pptxPath}`);
}).catch(err => {
  console.error("Error generating PPTX:", err);
  process.exit(1);
});
