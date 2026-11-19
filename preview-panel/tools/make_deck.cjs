// Builds samples/india_space_programme.pptx (demo deck) with PptxGenJS.
// node tools/make_deck.cjs <output.pptx>
const pptxgen = require("pptxgenjs");
const out = process.argv[2] || "samples/india_space_programme.pptx";
const p = new pptxgen();
p.layout = "LAYOUT_WIDE"; // 13.33 x 7.5 in
const NAVY = "0B1426", INK = "E9EEF6", MUTED = "93A2B8", AMBER = "F0B43C", TEAL = "4FD1C5", PANEL = "13213A";
const head = { fontFace: "Calibri", bold: true, color: INK };
const body = { fontFace: "Calibri", color: INK };

function base(title, kicker) {
  const s = p.addSlide();
  s.background = { color: NAVY };
  if (kicker) s.addText(kicker.toUpperCase(), { x: 0.7, y: 0.45, w: 10, h: 0.35, fontSize: 12, color: AMBER, charSpacing: 4, fontFace: "Consolas" });
  if (title) s.addText(title, { x: 0.7, y: 0.8, w: 12, h: 0.9, fontSize: 34, ...head });
  s.addShape(p.shapes.RECTANGLE, { x: 0, y: 7.3, w: 13.33, h: 0.2, fill: { color: AMBER } });
  return s;
}

// 1 cover
let s = p.addSlide();
s.background = { color: NAVY };
s.addShape(p.shapes.OVAL, { x: 8.2, y: -1.2, w: 7.5, h: 7.5, fill: { color: PANEL }, line: { color: TEAL, width: 1 } });
s.addShape(p.shapes.OVAL, { x: 9.6, y: 0.2, w: 4.7, h: 4.7, fill: { color: NAVY }, line: { color: AMBER, width: 1.5 } });
s.addText("DEMONSTRATION DECK · NOT FOR OPERATIONAL USE", { x: 0.7, y: 1.2, w: 9, h: 0.4, fontSize: 12, color: AMBER, charSpacing: 4, fontFace: "Consolas" });
s.addText("India in Space", { x: 0.7, y: 1.8, w: 9, h: 1.4, fontSize: 60, ...head });
s.addText("From Thumba to the lunar south pole", { x: 0.7, y: 3.2, w: 9, h: 0.7, fontSize: 26, color: MUTED, fontFace: "Calibri" });
s.addText("November 2026 · Prepared with Hermes", { x: 0.7, y: 6.3, w: 8, h: 0.4, fontSize: 14, color: MUTED, fontFace: "Consolas" });

// 2 stats
s = base("Four numbers that tell the story", "At a glance");
[["1969", "ISRO founded"], ["4th", "Country to soft-land on the Moon"], ["1st", "Asian nation in Mars orbit"], ["104", "Satellites on one launch (2017)"]].forEach(([v, l], i) => {
  const x = 0.7 + i * 3.05;
  s.addShape(p.shapes.LINE, { x, y: 2.4, w: 2.7, h: 0, line: { color: AMBER, width: 2 } });
  s.addText(v, { x, y: 2.6, w: 2.8, h: 1.4, fontSize: 64, bold: true, color: AMBER, fontFace: "Calibri" });
  s.addText(l, { x, y: 4.1, w: 2.7, h: 1.0, fontSize: 18, ...body, valign: "top" });
});

// 3 timeline
s = base("Milestones", "Six decades");
const ev = [["1963", "First rocket from Thumba"], ["1975", "Aryabhata"], ["1980", "SLV-3 orbits Rohini"], ["2008", "Chandrayaan-1"], ["2014", "Mars orbit"], ["2023", "Chandrayaan-3 lands"], ["2025", "SpaDeX docking"]];
s.addShape(p.shapes.LINE, { x: 0.9, y: 3.9, w: 11.6, h: 0, line: { color: MUTED, width: 2 } });
ev.forEach(([d, t], i) => {
  const x = 0.9 + i * 1.93;
  s.addShape(p.shapes.OVAL, { x: x - 0.14, y: 3.76, w: 0.28, h: 0.28, fill: { color: i === 5 ? AMBER : NAVY }, line: { color: AMBER, width: 2 } });
  s.addText(d, { x: x - 0.8, y: i % 2 ? 4.2 : 2.6, w: 1.6, h: 0.5, fontSize: 20, bold: true, color: AMBER, align: "center", fontFace: "Consolas" });
  s.addText(t, { x: x - 0.9, y: i % 2 ? 4.7 : 3.0, w: 1.8, h: 0.7, fontSize: 13, ...body, align: "center", valign: "top" });
});

// 4 compare
s = base("Three operational launch vehicles", "How India launches");
[["PSLV", "The workhorse", ["Polar and sun-synchronous orbits", "Chandrayaan-1, Mars Orbiter Mission"]],
 ["GSLV Mk II", "Indigenous cryogenic stage", ["Communication and navigation satellites", "Medium lift"]],
 ["LVM3", "Heavy lift", ["Chandrayaan-2 and -3", "Human-rated version for Gaganyaan"]]].forEach(([n, st, pts], i) => {
  const x = 0.7 + i * 4.1;
  s.addShape(p.shapes.LINE, { x, y: 2.2, w: 3.7, h: 0, line: { color: [INK, AMBER, TEAL][i], width: 4 } });
  s.addText(n, { x, y: 2.4, w: 3.7, h: 0.7, fontSize: 28, ...head });
  s.addText(st, { x, y: 3.1, w: 3.7, h: 0.5, fontSize: 16, italic: true, color: MUTED, fontFace: "Calibri" });
  s.addText(pts.map(t => ({ text: t, options: { bullet: true } })), { x, y: 3.7, w: 3.7, h: 2.2, fontSize: 17, ...body, valign: "top", paraSpaceAfter: 8 });
});

// 5 chart
s = base("Approximate payload to transfer orbit (kg)", "Capability");
s.addChart(p.charts.BAR, [{ name: "kg", labels: ["PSLV (sub-GTO)", "GSLV Mk II", "LVM3"], values: [1425, 2250, 4000] }], {
  x: 0.7, y: 1.9, w: 11.9, h: 4.9, barDir: "bar", chartColors: [AMBER], catAxisLabelColor: INK, valAxisLabelColor: MUTED,
  catAxisLabelFontSize: 16, valAxisLabelFontSize: 12, valGridLine: { color: "22324D", size: 1 }, showValue: true,
  dataLabelColor: INK, dataLabelFontSize: 14, catAxisLineShow: false, valAxisLineShow: false });

// 6 next
s = base("What comes next", "Outlook");
[["01", "Human spaceflight", "Gaganyaan: uncrewed tests first, then crew"], ["02", "A national space station", "Builds on the SpaDeX docking demonstration"],
 ["03", "Lunar sample return", "Chandrayaan-4"], ["04", "Private launchers", "A growing domestic launch industry"]].forEach(([n, t, b], i) => {
  const y = 2.0 + i * 1.25;
  s.addText(n, { x: 0.7, y, w: 1.2, h: 0.9, fontSize: 40, bold: true, color: AMBER, fontFace: "Calibri" });
  s.addText(t, { x: 2.0, y, w: 10, h: 0.5, fontSize: 22, ...head });
  s.addText(b, { x: 2.0, y: y + 0.5, w: 10, h: 0.45, fontSize: 16, color: MUTED, fontFace: "Calibri" });
});
s.addNotes("Demo deck for the preview panel. Facts are widely published public-record items; verify before operational use.");

p.writeFile({ fileName: out }).then(f => console.log("wrote", f));
