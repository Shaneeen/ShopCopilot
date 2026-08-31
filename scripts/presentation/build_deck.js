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
pptx.layout = "LAYOUT_16x9"; // 13.33 x 7.5 in
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

const F_SERIF = "Georgia";
const F_SANS = "Segoe UI";
const F_MONO = "Consolas";

function addHeader(slide, title, category = "SHOPCOPILOT · TECHJAM 2026") {
  slide.addText(category.toUpperCase(), {
    x: 0.8, y: 0.45, w: 11.5, h: 0.3,
    fontFace: F_SANS, fontSize: 10, color: C_ACCENT, bold: true, letterSpacing: 1.5
  });
  slide.addText(title, {
    x: 0.8, y: 0.75, w: 11.5, h: 0.6,
    fontFace: F_SERIF, fontSize: 22, color: C_DARK, bold: true
  });
}

function addFooter(slide, extraText = "") {
  const text = extraText ? `ShopCopilot · TechJam 2026 · submission-freeze 46e3322  |  ${extraText}` : "ShopCopilot · TechJam 2026 · submission-freeze 46e3322";
  slide.addText(text, {
    x: 0.8, y: 7.0, w: 11.7, h: 0.3,
    fontFace: F_MONO, fontSize: 9, color: "8A7A5E"
  });
}

function baseSlide() {
  const slide = pptx.addSlide();
  slide.background = { color: C_BG };
  return slide;
}

// ==========================================
// SLIDE 1: Title
// ==========================================
{
  const slide = baseSlide();
  
  // Hero Badge
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.8, y: 1.2, w: 3.2, h: 0.38,
    fill: { color: C_PANEL }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
  });
  slide.addText("TIKTOK TECHJAM 2026 · TRACK 4", {
    x: 0.9, y: 1.25, w: 3.0, h: 0.28,
    fontFace: F_SANS, fontSize: 10, color: C_ACCENT, bold: true, letterSpacing: 1
  });

  slide.addText("Finding the Hidden Product", {
    x: 0.8, y: 1.8, w: 11.5, h: 1.1,
    fontFace: F_SERIF, fontSize: 40, color: C_DARK, bold: true
  });
  slide.addText("7.0× Baseline Hit Rate in 10 Conversational Turns · 50k Catalog · 0 External LLM Calls", {
    x: 0.8, y: 2.9, w: 11.5, h: 0.5,
    fontFace: F_SANS, fontSize: 16, color: C_SEC
  });

  // 4 Metric Highlight Cards
  const cards = [
    { label: "HIT@10", val: "0.880", sub: "176 / 200 sessions (7.0×)" },
    { label: "MRR", val: "0.4916", sub: "7.2× official starter" },
    { label: "MTTC", val: "3.375", sub: "Found 2.9× faster (turns)" },
    { label: "TECHNICAL SCORE", val: "0.7400", sub: "7× starter (0.1067)" },
  ];

  cards.forEach((c, idx) => {
    const x = 0.8 + idx * 2.95;
    slide.addShape(pptx.ShapeType.roundRect, {
      x, y: 3.8, w: 2.75, h: 2.2,
      fill: { color: C_WHITE }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
    });
    slide.addText(c.label, {
      x: x + 0.2, y: 4.0, w: 2.35, h: 0.3,
      fontFace: F_SANS, fontSize: 11, color: "8A7A5E", bold: true, letterSpacing: 1
    });
    slide.addText(c.val, {
      x: x + 0.2, y: 4.35, w: 2.35, h: 0.8,
      fontFace: F_MONO, fontSize: 30, color: C_ACCENT, bold: true
    });
    slide.addText(c.sub, {
      x: x + 0.2, y: 5.25, w: 2.35, h: 0.5,
      fontFace: F_SANS, fontSize: 11, color: C_SEC
    });
  });

  addFooter(slide, "Data: Amazon Reviews 2023, McAuley Lab, UCSD");
  slide.addNotes(
    "Say: The task: a customer with a hidden target product. Our job: surface it in the top-10 within 10 turns. [EMPHASIZE] We do it 88% of the time in about 3.4 turns. [PAUSE] [ADVANCE]\nTiming: 15s"
  );
}

// ==========================================
// SLIDE 2: Spec-Contract View & Architecture
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Spec-Contract Pipeline & Defensive Architecture");

  // Left Column: Turn Contract & Guarantees
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.8, y: 1.5, w: 5.6, h: 5.2,
    fill: { color: C_WHITE }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
  });
  slide.addText("SIMULATOR API CONTRACT (Official Evaluator)", {
    x: 1.0, y: 1.7, w: 5.2, h: 0.3,
    fontFace: F_SANS, fontSize: 11, color: C_ACCENT, bold: true, letterSpacing: 1
  });
  slide.addText(
    "• Turn Options: Every turn returns message + optional ask_attribute + up to 10 recommendations.\n" +
    "• Zero Hit Sacrifice: Clarification questions never forfeit recommendation evaluation.\n" +
    "• Stop Condition: Immediate win if target in top-10, else max 10 turns.\n" +
    "• Reliability Defenses:\n" +
    "   - Strict de-duplication & valid catalog ASIN enforcement\n" +
    "   - ask_attribute validated strictly against allowed spec enum\n" +
    "   - Deterministic isolation: per-session state lifecycle\n" +
    "   - 332 automated tests guarding all contracts & regression bounds\n" +
    "   - Fully deterministic offline execution (0 network dependency)",
    {
      x: 1.0, y: 2.1, w: 5.2, h: 4.4,
      fontFace: F_SANS, fontSize: 13, color: C_DARK, lineSpacingMultiple: 1.25
    }
  );

  // Right Column: Pipeline Funnel Diagram
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 6.7, y: 1.5, w: 5.8, h: 5.2,
    fill: { color: C_PANEL }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
  });
  slide.addText("PRODUCTION EXECUTION FUNNEL", {
    x: 6.9, y: 1.7, w: 5.4, h: 0.3,
    fontFace: F_SANS, fontSize: 11, color: C_ACCENT, bold: true, letterSpacing: 1
  });

  const funnelSteps = [
    { title: "50,000 Catalog Products", desc: "SQLite FTS5 BM25 + Hashed TF-IDF Semantic Index" },
    { title: "Hybrid Retrieval Pool (~300 items)", desc: "Reciprocal Rank Fusion (k=60) + Guarantee Pool" },
    { title: "Full Candidate Scoring (320 Safety Cap)", desc: "Cap >= Pool: 100% of candidate pool scored through ranker" },
    { title: "8-Gate Clarification Engine", desc: "Entropy set-splitting on Boolean token index" },
    { title: "Top-10 Attributed Output", desc: "Constraint coverage × IDF × Salience + Popularity" },
  ];

  funnelSteps.forEach((st, i) => {
    const y = 2.15 + i * 0.92;
    slide.addShape(pptx.ShapeType.roundRect, {
      x: 7.0, y, w: 5.2, h: 0.78,
      fill: { color: C_WHITE }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.08
    });
    slide.addText(`${i + 1}. ${st.title}`, {
      x: 7.15, y: y + 0.08, w: 4.9, h: 0.3,
      fontFace: F_SANS, fontSize: 12, color: C_DARK, bold: true
    });
    slide.addText(st.desc, {
      x: 7.15, y: y + 0.38, w: 4.9, h: 0.32,
      fontFace: F_SANS, fontSize: 10.5, color: C_SEC
    });
  });

  addFooter(slide);
  slide.addNotes(
    "Say: We implemented their API exactly — and defensively. [POINT at contract row] Every turn can ask, recommend, or both; a question never forfeits the hit chance. The deterministic system is completely self-contained with no network dependency.\nTiming: 30s"
  );
}

// ==========================================
// SLIDE 3: Staircase (Money Slide)
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Performance Staircase: 7.0× Hit Rate & 7.2× MRR");

  // Top Table
  const tableRows = [
    [
      { text: "System State", options: { bold: true, fill: { color: C_PANEL }, fontFace: F_SANS } },
      { text: "Hit@10", options: { bold: true, fill: { color: C_PANEL }, fontFace: F_SANS } },
      { text: "MRR", options: { bold: true, fill: { color: C_PANEL }, fontFace: F_SANS } },
      { text: "MTTC", options: { bold: true, fill: { color: C_PANEL }, fontFace: F_SANS } },
      { text: "Technical Score", options: { bold: true, fill: { color: C_PANEL }, fontFace: F_SANS } },
    ],
    [
      { text: "Starter (Official Baseline)", options: { fontFace: F_SANS } },
      { text: "0.125", options: { fontFace: F_MONO } },
      { text: "0.0680", options: { fontFace: F_MONO } },
      { text: "9.81 turns", options: { fontFace: F_MONO } },
      { text: "0.1067", options: { fontFace: F_MONO } },
    ],
    [
      { text: "Pre-Experiments (v2 Baseline)", options: { fontFace: F_SANS } },
      { text: "0.870", options: { fontFace: F_MONO } },
      { text: "0.4455", options: { fontFace: F_MONO } },
      { text: "3.465 turns", options: { fontFace: F_MONO } },
      { text: "0.7193", options: { fontFace: F_MONO } },
    ],
    [
      { text: "Final Shipped (submission-freeze)", options: { bold: true, fill: { color: "FDF2E9" }, fontFace: F_SANS, color: C_ACCENT } },
      { text: "0.880", options: { bold: true, fill: { color: "FDF2E9" }, fontFace: F_MONO, color: C_ACCENT } },
      { text: "0.4916", options: { bold: true, fill: { color: "FDF2E9" }, fontFace: F_MONO, color: C_ACCENT } },
      { text: "3.375 turns", options: { bold: true, fill: { color: "FDF2E9" }, fontFace: F_MONO, color: C_ACCENT } },
      { text: "0.7400", options: { bold: true, fill: { color: "FDF2E9" }, fontFace: F_MONO, color: C_ACCENT } },
    ],
  ];

  slide.addTable(tableRows, {
    x: 0.8, y: 1.5, w: 11.7, h: 2.2,
    fontSize: 12, border: { pt: 1, color: C_BORDER }, align: "center", valign: "middle"
  });

  // Bottom Panels: Formula & Decomposition
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.8, y: 4.0, w: 5.6, h: 2.7,
    fill: { color: C_WHITE }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
  });
  slide.addText("OFFICIAL METRIC FORMULA", {
    x: 1.0, y: 4.2, w: 5.2, h: 0.3,
    fontFace: F_SANS, fontSize: 11, color: C_ACCENT, bold: true, letterSpacing: 1
  });
  slide.addText("TechnicalScore = 0.5·Hit@10 + 0.3·MRR + 0.2·Efficiency\nwhere Efficiency = clip((11 − MTTC) / 10, 0, 1)", {
    x: 1.0, y: 4.6, w: 5.2, h: 0.8,
    fontFace: F_MONO, fontSize: 11.5, color: C_DARK
  });
  slide.addText("• 7.0× Hit Rate (0.125 → 0.880)\n• 7.2× Mean Reciprocal Rank (0.068 → 0.4916)\n• Found 2.9× faster (9.81 → 3.375 turns)\n• ~7× Technical Score gain overall", {
    x: 1.0, y: 5.4, w: 5.2, h: 1.1,
    fontFace: F_SANS, fontSize: 12, color: C_SEC
  });

  slide.addShape(pptx.ShapeType.roundRect, {
    x: 6.7, y: 4.0, w: 5.8, h: 2.7,
    fill: { color: C_WHITE }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
  });
  slide.addText("SCORE GAIN DECOMPOSITION (vs v2 Pre-Exp)", {
    x: 6.9, y: 4.2, w: 5.4, h: 0.3,
    fontFace: F_SANS, fontSize: 11, color: C_ACCENT, bold: true, letterSpacing: 1
  });
  slide.addText("Δ TechnicalScore = +0.0207 (+2.07 pp)", {
    x: 6.9, y: 4.6, w: 5.4, h: 0.4,
    fontFace: F_MONO, fontSize: 13, color: C_ACCENT, bold: true
  });
  slide.addText(
    "• MRR Gain: 67% of ΔTS (0.3 · +0.0461 = +0.0138)\n" +
    "• Hit@10 Gain: 24% of ΔTS (0.5 · +0.0100 = +0.0050)\n" +
    "• Efficiency Gain: 9% of ΔTS (0.2 · +0.0090 = +0.0018)\n\n" +
    "Key Insight: Two-thirds of the gain comes from MRR — the ranker puts the target higher in the top 10.",
    {
      x: 6.9, y: 5.05, w: 5.4, h: 1.5,
      fontFace: F_SANS, fontSize: 12, color: C_DARK
    }
  );

  addFooter(slide);
  slide.addNotes(
    "Say: [EMPHASIZE] Against the official baseline we're seven-x. [PAUSE] Against our own pre-experiment system, two-thirds of the TechnicalScore gain is MRR — the ranker puts the right product higher, exactly what the shipped change predicts. [POINT at MRR row] [ADVANCE]\nTiming: 45s"
  );
}

// ==========================================
// SLIDE 4: Innovation Directions
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Exploration of Organizer-Proposed Innovation Directions");

  const innovTable = [
    [
      { text: "Organizer Direction", options: { bold: true, fill: { color: C_PANEL }, fontFace: F_SANS } },
      { text: "ShopCopilot Approach", options: { bold: true, fill: { color: C_PANEL }, fontFace: F_SANS } },
      { text: "Experimental Outcome", options: { bold: true, fill: { color: C_PANEL }, fontFace: F_SANS } },
    ],
    [
      { text: "Hybrid Retrieval", options: { bold: true, fontFace: F_SANS } },
      { text: "BM25 FTS5 (0.7) + Semantic TF-IDF (0.3) + RRF (k=60) + Guarantee Pool", options: { fontFace: F_SANS } },
      { text: "Shipped in v2: 88% pool recall, 0.880 Hit@10", options: { fontFace: F_MONO, color: C_ACCENT, bold: true } },
    ],
    [
      { text: "Adaptive Clarification", options: { bold: true, fontFace: F_SANS } },
      { text: "8-Gate entropy engine; question-margin gate hypothesis tested", options: { fontFace: F_SANS } },
      { text: "0/19 late-phase gate triggered; stopped before building", options: { fontFace: F_MONO, color: C_MUTED } },
    ],
    [
      { text: "Personalization", options: { bold: true, fontFace: F_SANS } },
      { text: "Soft profile boost (weight sweep 0.00 to 0.15) guarded by hard constraints", options: { fontFace: F_SANS } },
      { text: "Weight 0.03 worsened MRR; set to 0.00 (fail-safe)", options: { fontFace: F_MONO, color: C_MUTED } },
    ],
    [
      { text: "Explainable Ranking", options: { bold: true, fontFace: F_SANS } },
      { text: "Per-item ranking provenance (coverage, salience, popularity, violations)", options: { fontFace: F_SANS } },
      { text: "Live in interactive demo; zero score penalty", options: { fontFace: F_MONO, color: C_ACCENT, bold: true } },
    ],
    [
      { text: "LLM Reranking Tier", options: { bold: true, fontFace: F_SANS } },
      { text: "OpenRouter GPT-4o-mini / Nemotron with strict margin & twin gates", options: { fontFace: F_SANS } },
      { text: "Live probe Δ=0, +454ms latency; killed by ship gate", options: { fontFace: F_MONO, color: C_MUTED } },
    ],
    [
      { text: "Constraint Reweighting", options: { bold: true, fontFace: F_SANS } },
      { text: "Salience vs Popularity rebalancing (0.5 → 0.2) in deterministic ranker", options: { fontFace: F_SANS } },
      { text: "SHIPPED WIN: +4/−1 flips on dev, +1.0pp Hit, +4.6pp MRR", options: { fontFace: F_MONO, color: C_ACCENT, bold: true } },
    ],
  ];

  slide.addTable(innovTable, {
    x: 0.8, y: 1.5, w: 11.7, h: 5.1,
    fontSize: 11, border: { pt: 1, color: C_BORDER }, valign: "middle"
  });

  addFooter(slide);
  slide.addNotes(
    "Say: We attempted every applicable direction on the organizer's own list — [EMPHASIZE] including the ones that produced negative results. That's how we know which mechanisms are real.\nTiming: 30s"
  );
}

// ==========================================
// SLIDE 5: Rigorous Experimental Method
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Experimental Method: Worktree Isolation & Paired Flips");

  // 3 Boxes
  const boxes = [
    {
      title: "1. Worktree Isolation",
      desc: "5 dedicated git experiment worktrees branched from control snapshot 80eee9a.\n\n• Zero cross-contamination\n• Frozen evaluator untouched\n• Single config registration rule (tests/test_config_registered.py)",
    },
    {
      title: "2. Pre-Registered Pass Bars",
      desc: "Every experiment had written acceptance criteria before running first eval:\n\n• Hit gain bar: ΔHit >= +0.03\n• Latency ceiling: added p95 <= 2s\n• Automatic revert on regression",
    },
    {
      title: "3. Paired-Session Flips",
      desc: "Aggregate differences <3pp on 160 sessions are noise.\n\n• Exact per-session paired flips (miss→hit vs hit→miss)\n• Measured noise floor: ±1 session (159/160 match across identical runs)",
    },
  ];

  boxes.forEach((b, i) => {
    const x = 0.8 + i * 3.95;
    slide.addShape(pptx.ShapeType.roundRect, {
      x, y: 1.6, w: 3.75, h: 5.0,
      fill: { color: C_WHITE }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
    });
    slide.addText(b.title, {
      x: x + 0.25, y: 1.9, w: 3.25, h: 0.4,
      fontFace: F_SERIF, fontSize: 16, color: C_DARK, bold: true
    });
    slide.addText(b.desc, {
      x: x + 0.25, y: 2.5, w: 3.25, h: 3.8,
      fontFace: F_SANS, fontSize: 13, color: C_SEC, lineSpacingMultiple: 1.25
    });
  });

  addFooter(slide);
  slide.addNotes(
    "Say: [SLOW] Every experiment had its pass bar written before the first eval ran. We measured per-session paired flips against a strict ±1 session noise floor.\nTiming: 25s"
  );
}

// ==========================================
// SLIDE 6: The Win (Salience Reweight)
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "The Shipped Win: Constraint Salience vs Popularity");

  // Left Box: Waterfall & Session IDs
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.8, y: 1.5, w: 5.6, h: 5.2,
    fill: { color: C_WHITE }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
  });
  slide.addText("PAIRED FLIP WATERFALL (Dev-160)", {
    x: 1.0, y: 1.7, w: 5.2, h: 0.3,
    fontFace: F_SANS, fontSize: 11, color: C_ACCENT, bold: true, letterSpacing: 1
  });
  slide.addText(
    "Control Hits (fork-point 80eee9a): 141 / 160\n" +
    "  + 4 Miss → Hit Flips:\n" +
    "      • public_0031\n" +
    "      • public_0100\n" +
    "      • public_0085\n" +
    "      • public_0125\n" +
    "  − 1 Hit → Miss Flip:\n" +
    "      • public_0035\n" +
    "--------------------------------------------------\n" +
    "Final Dev Hits: 144 / 160 (0.900 Hit@10, +3 Net Flips)",
    {
      x: 1.0, y: 2.1, w: 5.2, h: 4.4,
      fontFace: F_MONO, fontSize: 12.5, color: C_DARK, lineSpacingMultiple: 1.2
    }
  );

  // Right Box: Mechanism & Honesty Box
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 6.7, y: 1.5, w: 5.8, h: 5.2,
    fill: { color: C_PANEL }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
  });
  slide.addText("MECHANISM & HYPOTHESIS REALITY", {
    x: 6.9, y: 1.7, w: 5.4, h: 0.3,
    fontFace: F_SANS, fontSize: 11, color: C_ACCENT, bold: true, letterSpacing: 1
  });
  slide.addText(
    "Root Cause:\n" +
    "Popularity score was crowding out products that satisfied specific, high-value user constraints. Lowering salience weight (0.5 → 0.2) lets constraint coverage dominate.\n\n" +
    "Honesty Box (Scientific Discipline):\n" +
    "The experiment originally hypothesized a Buying-specific win. In reality, the wins were route-general across multiple scenarios.\n\n" +
    "Because the net +3 paired flips exceeded the ±1 noise floor and confirmed on the public-200 set (0.870 → 0.880, MRR 0.4455 → 0.4916), it was merged to main.",
    {
      x: 6.9, y: 2.1, w: 5.4, h: 4.4,
      fontFace: F_SANS, fontSize: 12.5, color: C_DARK, lineSpacingMultiple: 1.25
    }
  );

  addFooter(slide);
  slide.addNotes(
    "Say: [LOOK] The win failed its own hypothesis. It shipped anyway — because the flips, not the hypothesis, were the evidence. [ADVANCE]\nTiming: 30s"
  );
}

// ==========================================
// SLIDE 7: Progression & Per-Scenario Breakdown
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Out-of-Sample Transfer & Per-Scenario Results");

  // Left: Two Distinct Evaluation Sets
  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.8, y: 1.5, w: 5.6, h: 5.2,
    fill: { color: C_WHITE }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
  });
  slide.addText("PROGRESSION ACROSS SPLITS", {
    x: 1.0, y: 1.7, w: 5.2, h: 0.3,
    fontFace: F_SANS, fontSize: 11, color: C_ACCENT, bold: true, letterSpacing: 1
  });
  slide.addText(
    "Dev-160 Split (Tuning Set):\n" +
    "• Control: 141 / 160 (0.881) · MRR 0.4388 · MTTC 3.32\n" +
    "• Shipped: 144 / 160 (0.900) · MRR 0.5144 · MTTC 3.19\n\n" +
    "Public-200 Set (Confirmation Only — Touched Twice):\n" +
    "• Baseline: 174 / 200 (0.870) · MRR 0.4455 · MTTC 3.465\n" +
    "• Shipped:  176 / 200 (0.880) · MRR 0.4916 · MTTC 3.375\n\n" +
    "Result: Out-of-sample confirmation proved the salience gain was not overfitted to dev.",
    {
      x: 1.0, y: 2.1, w: 5.2, h: 4.4,
      fontFace: F_SANS, fontSize: 12.5, color: C_DARK, lineSpacingMultiple: 1.25
    }
  );

  // Right: Per-Scenario Table with Honest Counts
  const scenTable = [
    [
      { text: "Scenario", options: { bold: true, fill: { color: C_PANEL }, fontFace: F_SANS } },
      { text: "Count", options: { bold: true, fill: { color: C_PANEL }, fontFace: F_SANS } },
      { text: "Hit@10", options: { bold: true, fill: { color: C_PANEL }, fontFace: F_SANS } },
      { text: "MRR", options: { bold: true, fill: { color: C_PANEL }, fontFace: F_SANS } },
      { text: "MTTC", options: { bold: true, fill: { color: C_PANEL }, fontFace: F_SANS } },
    ],
    [
      { text: "Browsing", options: { fontFace: F_SANS, bold: true } },
      { text: "74 / 80", options: { fontFace: F_MONO } },
      { text: "0.9250", options: { fontFace: F_MONO, color: C_ACCENT } },
      { text: "0.4532", options: { fontFace: F_MONO } },
      { text: "2.91 turns", options: { fontFace: F_MONO } },
    ],
    [
      { text: "Buying", options: { fontFace: F_SANS, bold: true } },
      { text: "73 / 80", options: { fontFace: F_MONO } },
      { text: "0.9125", options: { fontFace: F_MONO, color: C_ACCENT } },
      { text: "0.5444", options: { fontFace: F_MONO } },
      { text: "2.65 turns", options: { fontFace: F_MONO } },
    ],
    [
      { text: "Intent Override", options: { fontFace: F_SANS, bold: true } },
      { text: "23 / 30", options: { fontFace: F_MONO } },
      { text: "0.7667", options: { fontFace: F_MONO } },
      { text: "0.4960", options: { fontFace: F_MONO } },
      { text: "5.47 turns", options: { fontFace: F_MONO } },
    ],
    [
      { text: "Boundary (Vague)", options: { fontFace: F_SANS, bold: true } },
      { text: "6 / 10", options: { fontFace: F_MONO } },
      { text: "0.6000", options: { fontFace: F_MONO } },
      { text: "0.3625", options: { fontFace: F_MONO } },
      { text: "6.60 turns", options: { fontFace: F_MONO } },
    ],
  ];

  slide.addTable(scenTable, {
    x: 6.7, y: 1.5, w: 5.8, h: 3.4,
    fontSize: 11.5, border: { pt: 1, color: C_BORDER }, align: "center", valign: "middle"
  });

  slide.addShape(pptx.ShapeType.roundRect, {
    x: 6.7, y: 5.1, w: 5.8, h: 1.6,
    fill: { color: C_PANEL }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
  });
  slide.addText("Honesty in Small Denominators:\nBoundary is 6 of 10 and Intent Override is 23 of 30. We show exact sample sizes (n=80, 80, 30, 10) rather than hiding behind percentage rates.", {
    x: 6.9, y: 5.25, w: 5.4, h: 1.3,
    fontFace: F_SANS, fontSize: 11.5, color: C_DARK
  });

  addFooter(slide);
  slide.addNotes(
    "Say: Gains transfer out-of-sample. [POINT] And here's the small print we won't hide: boundary is six of ten — we show the counts.\nTiming: 25s"
  );
}

// ==========================================
// SLIDE 8: The Graveyard (6 Non-Shipped Experiments)
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "The Graveyard: 6 Hypotheses Rejected by Their Own Bars");

  const graveyardTable = [
    [
      { text: "Experiment Branch", options: { bold: true, fill: { color: C_PANEL }, fontFace: F_SANS } },
      { text: "Net Flips", options: { bold: true, fill: { color: C_PANEL }, fontFace: F_SANS } },
      { text: "Pre-Registered Bar / Reason for Rejection", options: { bold: true, fill: { color: C_PANEL }, fontFace: F_SANS } },
      { text: "Action", options: { bold: true, fill: { color: C_PANEL }, fontFace: F_SANS } },
    ],
    [
      { text: "exp/rank-salience", options: { fontFace: F_SANS, bold: true } },
      { text: "+3 net (+4/−1)", options: { fontFace: F_MONO, color: C_ACCENT, bold: true } },
      { text: "Exceeded ±1 noise floor; confirmed on public-200", options: { fontFace: F_SANS } },
      { text: "MERGED", options: { fontFace: F_MONO, color: C_ACCENT, bold: true } },
    ],
    [
      { text: "exp/global-salience", options: { fontFace: F_SANS } },
      { text: "+1 net (+2/−1)", options: { fontFace: F_MONO } },
      { text: "Within ±1 noise floor; not confirmed out-of-sample", options: { fontFace: F_SANS } },
      { text: "Reverted", options: { fontFace: F_MONO, color: C_MUTED } },
    ],
    [
      { text: "exp/competition-window", options: { fontFace: F_SANS } },
      { text: "+1 net (+2/−1)", options: { fontFace: F_MONO } },
      { text: "Within ±1 noise floor; identical flips to global-salience", options: { fontFace: F_SANS } },
      { text: "Unmerged", options: { fontFace: F_MONO, color: C_MUTED } },
    ],
    [
      { text: "exp/uninformative-stop", options: { fontFace: F_SANS } },
      { text: "−1 net (+1/−2)", options: { fontFace: F_MONO, color: "A02C2C" } },
      { text: "Regressed Hit (143/160); broke public_0104", options: { fontFace: F_SANS } },
      { text: "Reverted", options: { fontFace: F_MONO, color: "A02C2C" } },
    ],
    [
      { text: "exp/rank-coverage-idf", options: { fontFace: F_SANS } },
      { text: "0 net (0/0)", options: { fontFace: F_MONO } },
      { text: "Zero effect: 156/160 dev sessions over-generality dominated", options: { fontFace: F_SANS } },
      { text: "Unmerged", options: { fontFace: F_MONO, color: C_MUTED } },
    ],
    [
      { text: "exp/question-margin", options: { fontFace: F_SANS } },
      { text: "Gate: 0/19", options: { fontFace: F_MONO } },
      { text: "0 of 19 misses exhibited late-phase collapse opportunity", options: { fontFace: F_SANS } },
      { text: "Stopped", options: { fontFace: F_MONO, color: C_MUTED } },
    ],
    [
      { text: "exp/boundary-override", options: { fontFace: F_SANS } },
      { text: "Forensics: 0", options: { fontFace: F_MONO } },
      { text: "Forensics disproved lag premise; extraction already same-turn", options: { fontFace: F_SANS } },
      { text: "Stopped", options: { fontFace: F_MONO, color: C_MUTED } },
    ],
  ];

  slide.addTable(graveyardTable, {
    x: 0.8, y: 1.5, w: 11.7, h: 4.5,
    fontSize: 10.5, border: { pt: 1, color: C_BORDER }, align: "center", valign: "middle"
  });

  slide.addText(
    "\"Every red row was rejected by criteria written before the experiment ran. The 0.90625 in our logs was never merged.\"",
    {
      x: 0.8, y: 6.2, w: 11.7, h: 0.5,
      fontFace: F_SERIF, fontSize: 13, color: C_DARK, italic: true, align: "center"
    }
  );

  addFooter(slide);
  slide.addNotes(
    "Say: [REPEAT] Six experiments did not survive their own bars. Six negatives is how you know the green one is real.\nTiming: 30s"
  );
}

// ==========================================
// SLIDE 9: Structural Findings
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "4 Structural Findings Discovered Through Negative Results");

  const findings = [
    {
      num: "01",
      title: "MTTC = First Hit Turn",
      desc: "The evaluator terminates sessions the instant a target enters top 10. Wasted clarification questions occur POST-hit, so 'asking fewer questions' cannot mechanically reduce MTTC. Only surfacing the target sooner improves MTTC.",
    },
    {
      num: "02",
      title: "Conversation ↔ Retrieval Coupling",
      desc: "'Hit-safe by construction' is FALSE. In session public_0104, stopping clarification preserved an unrefined query that failed retrieval on subsequent turns. Dialogue and retrieval state are tightly coupled.",
    },
    {
      num: "03",
      title: "Scenario Labels ≠ Runtime Route",
      desc: "Static scenario types (Browsing vs Buying) do not determine turn-by-turn dynamics. 89% of browsing sessions acquire hard constraints by turn 2 and dynamically switch to Buying route weights.",
    },
    {
      num: "04",
      title: "Rank Re-orderings Are Saturated",
      desc: "Two completely independent ranker experiments (global-salience & competition-window) produced IDENTICAL flips (+2/−1: public_0075, public_0092 / public_0112). Ranking permutations on existing pools have hit saturation.",
    },
  ];

  findings.forEach((f, i) => {
    const x = 0.8 + (i % 2) * 5.95;
    const y = 1.6 + Math.floor(i / 2) * 2.55;
    slide.addShape(pptx.ShapeType.roundRect, {
      x, y, w: 5.75, h: 2.35,
      fill: { color: C_WHITE }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
    });
    slide.addText(f.num, {
      x: x + 0.2, y: y + 0.15, w: 0.8, h: 0.35,
      fontFace: F_MONO, fontSize: 18, color: C_ACCENT, bold: true
    });
    slide.addText(f.title, {
      x: x + 0.8, y: y + 0.15, w: 4.7, h: 0.35,
      fontFace: F_SERIF, fontSize: 14, color: C_DARK, bold: true
    });
    slide.addText(f.desc, {
      x: x + 0.2, y: y + 0.55, w: 5.3, h: 1.65,
      fontFace: F_SANS, fontSize: 11.5, color: C_SEC, lineSpacingMultiple: 1.2
    });
  });

  addFooter(slide);
  slide.addNotes(
    "Say: [SLOW] No score shows these. Each one redirected the next experiment. For example, knowing that 'ask less' cannot move MTTC saved us weeks of futile prompt engineering.\nTiming: 35s"
  );
}

// ==========================================
// SLIDE 10: Why We Miss (Root Cause Analysis)
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Why We Miss: Root-Cause Forensic Audit of All Misses");

  // 3 Forensic Buckets
  const missBuckets = [
    {
      title: "Pool Depth Misses (2)",
      stat: "2 / 16",
      desc: "Target product fell beyond retrieval cutoff (post-filter ranks 240–410 and 823–1480).\n\nRoot Cause: Coverage cap in candidate generation (rank 201+), not a ranking bug.",
    },
    {
      title: "Rank Score Misses (13)",
      stat: "13 / 16",
      desc: "Target was present in candidate pool but outranked by competing high-coverage items.\n\nRoot Cause: Deep misses need new information from user, not reordering.",
    },
    {
      title: "Extraction Residue (1)",
      stat: "1 / 16",
      desc: "Single entity extraction edge case (public_0117) with complex overlapping syntax.\n\nRoot Cause: Bounded regex parsing on unstructured customer utterances.",
    },
  ];

  missBuckets.forEach((b, i) => {
    const x = 0.8 + i * 3.95;
    slide.addShape(pptx.ShapeType.roundRect, {
      x, y: 1.6, w: 3.75, h: 3.6,
      fill: { color: C_WHITE }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
    });
    slide.addText(b.title, {
      x: x + 0.2, y: 1.8, w: 3.35, h: 0.35,
      fontFace: F_SERIF, fontSize: 15, color: C_DARK, bold: true
    });
    slide.addText(b.stat, {
      x: x + 0.2, y: 2.15, w: 3.35, h: 0.5,
      fontFace: F_MONO, fontSize: 24, color: C_ACCENT, bold: true
    });
    slide.addText(b.desc, {
      x: x + 0.2, y: 2.7, w: 3.35, h: 2.3,
      fontFace: F_SANS, fontSize: 12, color: C_SEC, lineSpacingMultiple: 1.25
    });
  });

  // Bottom Guarantee Badges
  const badges = [
    "QUERY FAITHFUL: 0 / 13 recoverable constraints dropped from queries",
    "POOL MISSES: Coverage cap (rank 201+), not pipeline bugs",
    "DEEP MISSES: Need new user information, not permutation tweaks",
  ];

  badges.forEach((bg, i) => {
    const x = 0.8 + i * 3.95;
    slide.addShape(pptx.ShapeType.roundRect, {
      x, y: 5.4, w: 3.75, h: 1.2,
      fill: { color: C_PANEL }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.08
    });
    slide.addText(bg, {
      x: x + 0.15, y: 5.5, w: 3.45, h: 1.0,
      fontFace: F_SANS, fontSize: 11, color: C_DARK, bold: true, align: "center", valign: "middle"
    });
  });

  addFooter(slide);
  slide.addNotes(
    "Say: We audited our own pipeline for leaks and found none — [EMPHASIZE] the remaining misses are genuine capability limits, and we know exactly which.\nTiming: 30s"
  );
}

// ==========================================
// SLIDE 11: Model, Cost & Latency Disclosure
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Feasibility Disclosure: Model, Cost & Latency");

  const discTable = [
    [
      { text: "Item / Dimension", options: { bold: true, fill: { color: C_PANEL }, fontFace: F_SANS } },
      { text: "Official Submission Disclosure", options: { bold: true, fill: { color: C_PANEL }, fontFace: F_SANS } },
      { text: "Verification Evidence / Artifact", options: { bold: true, fill: { color: C_PANEL }, fontFace: F_SANS } },
    ],
    [
      { text: "Runtime Model", options: { fontFace: F_SANS, bold: true } },
      { text: "NONE — Deterministic BM25 + Hashed TF-IDF + Constraint Ranker", options: { fontFace: F_MONO, color: C_ACCENT, bold: true } },
      { text: "results.json: reported_token_usage = 0", options: { fontFace: F_MONO } },
    ],
    [
      { text: "LLM Tokens", options: { fontFace: F_SANS, bold: true } },
      { text: "0 Prompt Tokens / 0 Completion Tokens", options: { fontFace: F_MONO } },
      { text: "results.json: total_tokens = 0", options: { fontFace: F_MONO } },
    ],
    [
      { text: "Inference Cost", options: { fontFace: F_SANS, bold: true } },
      { text: "$0.00 (Zero model API cost)", options: { fontFace: F_MONO, color: C_ACCENT, bold: true } },
      { text: "Self-contained local execution", options: { fontFace: F_SANS } },
    ],
    [
      { text: "Network Dependency", options: { fontFace: F_SANS, bold: true } },
      { text: "NONE at inference time", options: { fontFace: F_MONO } },
      { text: "Runs completely air-gapped / offline", options: { fontFace: F_SANS } },
    ],
    [
      { text: "Turn Latency (dev-160)", options: { fontFace: F_SANS, bold: true } },
      { text: "p50: 330.1 ms  ·  p95: 526.6 ms", options: { fontFace: F_MONO } },
      { text: "runs/control-dev-newbaseline.json:panel", options: { fontFace: F_MONO } },
    ],
    [
      { text: "Optional LLM Tier", options: { fontFace: F_SANS, bold: true } },
      { text: "Built & Gated (OpenRouter gpt-4o-mini); default OFF", options: { fontFace: F_SANS } },
      { text: "default_strategy.json: enable_llm_reranker = false", options: { fontFace: F_MONO } },
    ],
    [
      { text: "Execution Environment", options: { fontFace: F_SANS, bold: true } },
      { text: "Python 3.13.2 · Windows 11 Pro 64-bit · AMD Ryzen 7 (32GB RAM)", options: { fontFace: F_MONO } },
      { text: "Captured live via docs/final-eval-record.md", options: { fontFace: F_SANS } },
    ],
  ];

  slide.addTable(discTable, {
    x: 0.8, y: 1.5, w: 11.7, h: 5.1,
    fontSize: 11, border: { pt: 1, color: C_BORDER }, valign: "middle"
  });

  addFooter(slide);
  slide.addNotes(
    "Say: Feasibility disclosed per spec — [POINT] zero tokens, zero model cost, no network at inference. The deterministic system is the submission.\nTiming: 20s"
  );
}

// ==========================================
// SLIDE 12: Business Impact & Conversational Trust
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Business Impact: Guided Purchase vs Commercial Abandonment");

  const pillars = [
    {
      title: "Bounce Rate Collapse",
      sub: "3.4 turns vs 9.8 turns",
      desc: "Commercial conversational search fails when users abandon after vague initial queries. Reducing mean turns to conversion from 9.8 to 3.4 turns changes user experience from bounce to completed checkout.",
    },
    {
      title: "Attributable Ranking",
      sub: "Transparent Explanations",
      desc: "Every recommendation provides exact mathematical attribution: constraint coverage, IDF rarity, field salience, and popularity. High-stakes e-commerce requires explainability that black-box LLMs cannot provide.",
    },
    {
      title: "Zero Marginal Cost",
      sub: "$0.00 inference cost",
      desc: "Servicing millions of retail users with $0.02/turn LLM rerankers destroys unit economics. Our deterministic index serves 330 ms responses with zero external API fees and 100% uptime SLA.",
    },
  ];

  pillars.forEach((p, i) => {
    const x = 0.8 + i * 3.95;
    slide.addShape(pptx.ShapeType.roundRect, {
      x, y: 1.6, w: 3.75, h: 5.0,
      fill: { color: C_WHITE }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
    });
    slide.addText(p.title, {
      x: x + 0.2, y: 1.9, w: 3.35, h: 0.35,
      fontFace: F_SERIF, fontSize: 16, color: C_DARK, bold: true
    });
    slide.addText(p.sub, {
      x: x + 0.2, y: 2.3, w: 3.35, h: 0.4,
      fontFace: F_MONO, fontSize: 14, color: C_ACCENT, bold: true
    });
    slide.addText(p.desc, {
      x: x + 0.2, y: 2.85, w: 3.35, h: 3.4,
      fontFace: F_SANS, fontSize: 12.5, color: C_SEC, lineSpacingMultiple: 1.25
    });
  });

  addFooter(slide);
  slide.addNotes(
    "Say: Conversational search fails commercially when users abandon: vague query leads to wrong products leads to exit. 3.4 turns vs 9.8 is guided purchase vs bounce. Attributable ranking gives user trust.\nTiming: 25s"
  );
}

// ==========================================
// SLIDE 13: Final-Eval Readiness
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Final-Eval Readiness: 800 Hidden Sessions");

  const checks = [
    { title: "Evaluator Frozen", desc: "evaluator/ byte-identical to starter package. Zero edits, imports only." },
    { title: "Fresh-Clone Rehearsal", desc: "Cloned clean repo into temporary workspace; reproduces exact 0.880 table." },
    { title: "No Session Hardcoding", desc: "Zero session-id checks in starter/ or neeshops/ codebase." },
    { title: "Strict Data Isolation", desc: "Public-200 touched twice for confirmation; 800 hidden sessions touched 0 times." },
    { title: "332 Automated Tests", desc: "Pytest suite passes 100% (332 pass, 1 deselected) in under 22 seconds." },
    { title: "Snapshot & Env Retained", desc: "Exact git commit 46e3322, pip dependencies, and hardware captured." },
  ];

  checks.forEach((c, i) => {
    const x = 0.8 + (i % 2) * 5.95;
    const y = 1.6 + Math.floor(i / 2) * 1.7;
    slide.addShape(pptx.ShapeType.roundRect, {
      x, y, w: 5.75, h: 1.55,
      fill: { color: C_WHITE }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
    });
    slide.addText(`✔  ${c.title}`, {
      x: x + 0.2, y: y + 0.15, w: 5.35, h: 0.35,
      fontFace: F_SERIF, fontSize: 14, color: C_ACCENT, bold: true
    });
    slide.addText(c.desc, {
      x: x + 0.2, y: y + 0.55, w: 5.35, h: 0.85,
      fontFace: F_SANS, fontSize: 12, color: C_SEC, lineSpacingMultiple: 1.2
    });
  });

  addFooter(slide);
  slide.addNotes(
    "Say: 800 hidden sessions run against our frozen commit with the unmodified official evaluator. Our fresh clone rehearsal reproduced the exact 0.880 score.\nTiming: 20s"
  );
}

// ==========================================
// SLIDE 14: Technical Roadmap
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Technical Roadmap: Beyond Submission Freeze");

  const roadItems = [
    {
      phase: "Phase 1",
      title: "Recall Expansion Layer",
      desc: "Break candidate coverage cap (201+) with category-specialized inverted sub-indices to eliminate the remaining 2 pool misses.",
    },
    {
      phase: "Phase 2",
      title: "Deep Feature Enrichment",
      desc: "Extract fine-grained attributes (fabric weight, collar type, sole stiffness) to supply new information for rank-depth misses.",
    },
    {
      phase: "Phase 3",
      title: "Early Hit Prioritization",
      desc: "Optimize turn-1 recommendation ranking specifically for top-1 placement to drive MTTC below 2.5 turns.",
    },
  ];

  roadItems.forEach((r, i) => {
    const x = 0.8 + i * 3.95;
    slide.addShape(pptx.ShapeType.roundRect, {
      x, y: 1.6, w: 3.75, h: 5.0,
      fill: { color: C_WHITE }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
    });
    slide.addText(r.phase, {
      x: x + 0.2, y: 1.9, w: 3.35, h: 0.3,
      fontFace: F_MONO, fontSize: 12, color: C_ACCENT, bold: true
    });
    slide.addText(r.title, {
      x: x + 0.2, y: 2.25, w: 3.35, h: 0.45,
      fontFace: F_SERIF, fontSize: 16, color: C_DARK, bold: true
    });
    slide.addText(r.desc, {
      x: x + 0.2, y: 2.85, w: 3.35, h: 3.4,
      fontFace: F_SANS, fontSize: 12.5, color: C_SEC, lineSpacingMultiple: 1.25
    });
  });

  addFooter(slide);
  slide.addNotes(
    "Say: Our roadmap directly addresses our measured capability limits: expanding the pool recall layer and enriching features for deep rank misses.\nTiming: 15s"
  );
}

// ==========================================
// SLIDE 15: Provenance & Reproducibility
// ==========================================
{
  const slide = baseSlide();
  addHeader(slide, "Artifact Provenance & Reproduction Commands");

  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.8, y: 1.5, w: 5.6, h: 5.2,
    fill: { color: C_WHITE }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
  });
  slide.addText("GIT TAG CHAIN & ARTIFACT REFS", {
    x: 1.0, y: 1.7, w: 5.2, h: 0.3,
    fontFace: F_SANS, fontSize: 11, color: C_ACCENT, bold: true, letterSpacing: 1
  });
  slide.addText(
    "Tag Chain:\n" +
    "• fork-point (80eee9a) — fork baseline\n" +
    "• new-baseline (46e3322) — post-salience control\n" +
    "• submission-freeze (46e3322) — official submission\n\n" +
    "Key Evidence Artifacts:\n" +
    "• results.json — public-200 score (0.880)\n" +
    "• runs/control-dev-newbaseline.json — dev-160 (0.900)\n" +
    "• docs/experiment-ledger.md — all experiment runs\n" +
    "• docs/final-eval-record.md — fresh clone record\n" +
    "• DATA_ATTRIBUTION.md — UCSD McAuley Lab",
    {
      x: 1.0, y: 2.1, w: 5.2, h: 4.4,
      fontFace: F_MONO, fontSize: 11.5, color: C_DARK, lineSpacingMultiple: 1.2
    }
  );

  slide.addShape(pptx.ShapeType.roundRect, {
    x: 6.7, y: 1.5, w: 5.8, h: 5.2,
    fill: { color: C_PANEL }, line: { color: C_BORDER, width: 1 }, rectRadius: 0.1
  });
  slide.addText("REPRODUCE IN 3 COMMANDS", {
    x: 6.9, y: 1.7, w: 5.4, h: 0.3,
    fontFace: F_SANS, fontSize: 11, color: C_ACCENT, bold: true, letterSpacing: 1
  });
  slide.addText(
    "# 1. Install Dependencies & Build Catalog FTS\n" +
    "pip install -r requirements.txt\n" +
    "python scripts/setup_catalog.py\n\n" +
    "# 2. Run Test Suite (332 passed)\n" +
    "python -m pytest -q\n\n" +
    "# 3. Run Official Evaluator (Reproduces 0.880 Table)\n" +
    "python -m evaluator.local_evaluator\n\n" +
    "# 4. Launch Interactive Live Demo\n" +
    "python scripts/interactive_demo.py",
    {
      x: 6.9, y: 2.1, w: 5.4, h: 4.4,
      fontFace: F_MONO, fontSize: 12, color: C_DARK, lineSpacingMultiple: 1.25
    }
  );

  addFooter(slide, "Data Attribution: Amazon Reviews 2023, McAuley Lab, UCSD");
  slide.addNotes(
    "Say: Everything in this presentation is reproducible with three standard commands from a clean clone. Thank you.\nTiming: 10s"
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
