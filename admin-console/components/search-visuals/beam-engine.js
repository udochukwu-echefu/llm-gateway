/* Adapted from voice-glow 0.2.1. The original geometry, layers, smoothing, scan and distortion are retained. CSS is extracted locally; dynamic motion uses Web Animations without style attributes. Audio/microphone code is omitted.
MIT License

Copyright (c) 2026 Jakub Antalik

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
*/

const Ua = 36;
const we = [
  {
    x: 0,
    w: 74,
    h: 46,
    band: 0,
  },
  {
    x: -36,
    w: 54,
    h: 40,
    band: 1,
  },
  {
    x: 36,
    w: 54,
    h: 40,
    band: 1,
  },
  {
    x: -72,
    w: 48,
    h: 32,
    band: 2,
  },
  {
    x: 72,
    w: 48,
    h: 32,
    band: 2,
  },
  {
    x: -108,
    w: 42,
    h: 26,
    band: 1,
  },
  {
    x: 108,
    w: 42,
    h: 26,
    band: 1,
  },
];
const Ka = Ua * we.length;
const Ue = {
  dark: { core: "255, 255, 255", above: "255, 70, 80", mid: "90, 255, 150", below: "80, 140, 255" },
  light: {
    core: "197, 139, 255",
    above: "255, 122, 182",
    mid: "126, 196, 255",
    below: "45, 255, 171",
  },
};
const Rn = {
  scale: 1,
  glowSize: 1,
  processingDuration: 1.1,
  processingLevel: 0.55,
  processingTravel: 1.55,
  processingCurve: 2.1,
  cornerFollow: 0.45,
  strokeOpacity: 1,
  innerOpacity: 1,
  bloomOpacity: 1,
  idle: 0.18,
  reach: 1.2,
  spread: 1.05,
  flow: 48,
  bend: 60,
  bandStrength: 1.55,
  bandWidth: 2.15,
  bandPosition: 0.35,
  bandCurve: 1.75,
  bandSpread: 0.87,
  bandSkew: 0.12,
  bandOffset: -27,
  bandTail: 0.59,
  bandTailPosition: 0.67,
  bandTailCurve: 2.4,
  bandTailOverflow: 15,
  bandAberration: 0.89,
  distortion: 0.62,
  distortionDetail: 2.3,
  glowWidth: 0.65,
  glowHeight: 1.25,
  lobeSpacing: 0.85,
  rangeWidth: 0.75,
  rangeHeight: 1,
  softness: 1.07,
  coreSize: 1,
  coreLight: 0,
  coreLightWidth: 1,
  coreLightHeight: 1,
  strokeScale: 1,
  innerScale: 1,
  innerHeight: 1,
  bloomScale: 1,
  bloomHeight: 1,
};
function Sa(n) {
  return n < 0 ? 0 : n > 1 ? 1 : n;
}
function sn(n, e) {
  const a = e / 2;
  return ((((n + a) % e) + e) % e) - a;
}
function cn(n, e) {
  const a = n / (e / 2 + 4);
  return Math.max(0, 1 - a * a);
}
function pa(n, e) {
  if (n <= e) return 0;
  const a = (n - e) / Math.max(1e-3, 1 - e);
  return Sa((1 - Math.exp(-3 * a)) / (1 - Math.exp(-3)));
}
function Ge(n, e, a, r, t) {
  const s = e > n ? r : t,
    o = 1 - Math.exp(-a / Math.max(1e-3, s));
  return n + (e - n) * o;
}
function $n(n, e, a, r) {
  const t = n < 0 ? 1 - r : 1 + r,
    s = Math.max(0.05, a * t),
    o = Math.exp(-Math.pow(Math.abs(n) / s, e)),
    i = Math.exp(-Math.pow(1 / s, e));
  return Math.max(0, (o - i) / (1 - i));
}
function wn(n, e, a, r, t) {
  if (a <= 0 || e <= 0) return 0;
  const s = e * Math.max(0, Math.min(0.98, r));
  if (n <= s) return 0;
  const o = Math.min(1, (n - s) / Math.max(1, e - s));
  return a * Math.pow(o, Math.max(0.5, t));
}
function Ta(n, e, a) {
  return Math.max(0, Math.min(n, e / 2, a / 2));
}
function gt(n, e, a, r = 0) {
  if (a <= 0) return 0;
  const t = Math.min(n, e - n) - r;
  if (t >= a) return 0;
  if (t <= 0) return a;
  const s = a - t;
  return a - Math.sqrt(Math.max(0, a * a - s * s));
}
function xn(n, e, a, r) {
  const t = a / 2 + e.cx * e.w,
    s = vn * n.rangeWidth * e.w * e.mw,
    o = r * 0.82 * Math.min(1, n.scale),
    i = Math.min(o, (mn * n.rangeHeight * e.h + e.lift) * n.bandPosition),
    u = r - n.bandOffset,
    l = Math.min(1, e.corner * 4),
    p = n.bandTail * (1 - l * l * (3 - 2 * l)),
    b = p > 1e-3,
    m = b ? n.bandTailOverflow : 0,
    d = b ? -m : t - s,
    h = b ? a + m : t + s,
    T = [];
  for (let O = 0; O <= ma; O++) {
    const L = d + ((h - d) * O) / ma,
      _ = Math.max(-1, Math.min(1, (L - t) / Math.max(1, s))),
      G = (L < t ? t : a - t) + m,
      U =
        $n(_, n.bandCurve, n.bandSpread, n.bandSkew) +
        wn(Math.abs(L - t), G, p, n.bandTailPosition, n.bandTailCurve),
      E = e.corner > 0 ? gt(L, a, Ta(n.radius, a, r)) * e.corner : 0;
    T.push([L, u - i * U - E]);
  }
  return T;
}
function yn(n, e, a, r, t) {
  for (const [s, o] of [
    ["", 1],
    ["-z", 0.5],
  ]) {
    const i = (b) => (b * o).toFixed(1) + "px",
      u = a.map(([b, m]) => `${i(b)} ${i(m)}`),
      l = `polygon(0 ${i(t)}, ${u.join(", ")}, ${i(r)} ${i(t)})`,
      p = `polygon(0 0, ${i(r)} 0, ${i(r)} ${i(t)}, ${u.slice().reverse().join(", ")}, 0 ${i(t)})`;
    writeProperty(`--vb-clip-below${s}-${e}`, l);
    writeProperty(`--vb-clip-above${s}-${e}`, p);
  }
}
function Mn(n, e, a) {
  let r = a;
  for (let i = 0; i < e.length; i++)
    if (e[i][1] < r) {
      r = e[i][1];
    }
  const t = Math.max(0, Math.min(0.9, Math.floor((r - gn) / a / fa) * fa));
  if (t === n.filterTop) return;
  n.filterTop = t;
  const s = 1 + Math.max(fn, pn / a),
    o = n.filter;
  o.setAttribute("x", `${-va * 100}%`);
  o.setAttribute("width", `${(1 + 2 * va) * 100}%`);
  o.setAttribute("y", `${(t * 100).toFixed(0)}%`);
  o.setAttribute("height", `${((s - t) * 100).toFixed(1)}%`);
}
function Sn(n, e, a) {
  const { canvas: r, ctx: t, el: s, config: o } = n;
  if (!r || !t) return;
  const i = s.clientWidth,
    u = s.clientHeight;
  if (!i || !u) return;
  const l = Math.min(ln, (typeof window < "u" && window.devicePixelRatio) || 1),
    p = Math.round(i * l),
    b = Math.round(u * l);
  if (r.width !== p || r.height !== b) {
    r.width = p;
    r.height = b;
  }
  t.setTransform(l, 0, 0, l, 0, 0);
  t.clearRect(0, 0, i, u);
  const m = n.haloCanvas,
    d = n.haloCtx;
  if (m && d) {
    if (m.width !== p || m.height !== b) {
      m.width = p;
      m.height = b;
    }
    d.setTransform(l, 0, 0, l, 0, 0);
    d.clearRect(0, 0, i, u);
  }
  const h = Math.min(1, 0.6 * o.bandStrength * e.strength);
  if (h < 5e-3 || o.bandWidth <= 0) return;
  const T = o.theme === "dark",
    O = o.bandWidth * (1 + 0.35 * e.level),
    L = o.bandAberration * (0.35 + 0.65 * e.level),
    _ = (4 + 12 * L) * o.scale,
    G = 4 * L * o.scale,
    U = (v, k) => {
      t.beginPath();
      t.moveTo(a[0][0] + v, a[0][1] + k);
      for (let w = 1; w < a.length; w++) t.lineTo(a[w][0] + v, a[w][1] + k);
    },
    E = {
      r: o.bandColors.above,
      g: o.bandColors.mid,
      c: o.bandColors.core,
      b: o.bandColors.below,
    },
    D = (T ? 0.42 : 0.4) * h,
    C = 14 * O,
    z = (3.5 * o.bandWidth) / 2,
    g = z * l,
    H = typeof t.filter == "string",
    Q = H ? "0px" : `${z.toFixed(2)}px`;
  if (n.cssBlur !== Q) {
    writeProperty(`--vb-band-blur-${o.id}`, Q);
    writeProperty(`--vb-band-halo-blur-${o.id}`, H ? "0px" : `${(z * 3).toFixed(2)}px`);
    n.cssBlur = Q;
  }
  const le = [
      [1, 0.16],
      [0.72, 0.2],
      [0.46, 0.26],
      [0.22, 0.34],
    ],
    K = [
      {
        rgb: E.r,
        a: 1,
        ox: G,
        oy: -_,
      },
      {
        rgb: E.g,
        a: 0.55,
        ox: G * 0.35,
        oy: -_ * 0.35,
      },
      {
        rgb: E.b,
        a: 1,
        ox: -G,
        oy: _,
      },
      {
        rgb: E.c,
        a: 0.9,
        ox: 0,
        oy: 0,
      },
    ];
  t.lineCap = "round";
  t.lineJoin = "round";
  t.globalCompositeOperation = "source-over";
  const W = a[0][0],
    R = a[a.length - 1][0],
    I = (v, k) => {
      const w = t.createLinearGradient(W, 0, R, 0),
        S = o.bandTail > 0 ? 0.015 : 0.18;
      return (
        w.addColorStop(0, `rgba(${v}, 0)`),
        w.addColorStop(S, `rgba(${v}, ${k.toFixed(3)})`),
        w.addColorStop(1 - S, `rgba(${v}, ${k.toFixed(3)})`),
        w.addColorStop(1, `rgba(${v}, 0)`),
        w
      );
    },
    P = !H && d ? d : t;
  if (H) {
    t.filter = `blur(${(g * 3).toFixed(1)}px)`;
  }
  P.lineCap = "round";
  P.lineJoin = "round";
  P.strokeStyle = I(E.c, D * 0.3);
  P.lineWidth = C * 2.2;
  P.beginPath();
  P.moveTo(a[0][0], a[0][1]);
  for (let v = 1; v < a.length; v++) P.lineTo(a[v][0], a[v][1]);
  P.stroke();
  if (H) {
    t.filter = `blur(${g.toFixed(1)}px)`;
  }
  for (const v of K)
    for (const [k, w] of le) {
      t.strokeStyle = I(v.rgb, D * v.a * w);
      t.lineWidth = Math.max(0.6, C * k);
      U(v.ox, v.oy);
      t.stroke();
    }
  if (H) {
    t.filter = "none";
  }
  t.globalCompositeOperation = "source-over";
}
function Tn(n) {
  return (1 - Math.cos(Ma * n)) / 2;
}
const ln = 2,
  dn = 0.06,
  hn = 0.35,
  bn = 0.03,
  un = !(
    typeof navigator !== "undefined" &&
    /AppleWebKit/.test(navigator.userAgent) &&
    !/Chrome\/|Chromium\/|Edg\/|OPR\//.test(navigator.userAgent)
  ),
  fa = 0.05,
  gn = 6,
  pn = 12,
  fn = 0.1,
  va = 0.1,
  vn = 170,
  mn = 64,
  ma = 56,
  Ma = Math.PI * 2;
let properties;
function writeProperty(key, value) {
  properties[key] = value;
}
export function createBeam(host, canvas, halo) {
  const config = {
    ...Rn,
    id: "search",
    theme: "dark",
    radius: 37,
    sensitivity: 3.1,
    threshold: 0.015,
    attack: 0.325,
    release: 0.86,
    breatheDuration: 5.2,
    bands: true,
    processing: false,
    processingEase: 0.6,
    hueRange: 24,
    hueDuration: 12,
    staticColors: false,
    reducedMotion: false,
    paused: false,
    bandColors: Ue.dark,
  };
  const actor = {
    el: host,
    config,
    source: {
      getLevel: () => 0,
    },
    canvas,
    ctx: canvas.getContext("2d"),
    haloCanvas: halo,
    haloCtx: halo.getContext("2d"),
    displace: host.querySelector("feDisplacementMap"),
    noiseShift: host.querySelector("feOffset"),
    filter: host.querySelector("filter"),
    filterTop: -1,
    cssBlur: null,
    warpOff: false,
    s: {
      level: 0,
      bands: [0, 0, 0],
      phase: 0,
      scanA: 0,
      scanT: 0,
      t: 0,
      lastTs: 0,
      warp: 1,
    },
  };
  const animation = host.animate([{}], {
    duration: 1,
    fill: "forwards",
  });
  return {
    paint(now, level, processing, reducedMotion) {
      properties = {};
      if (config.processing !== processing || config.reducedMotion !== reducedMotion)
        actor.paintedConfig = null;
      config.processing = processing;
      config.reducedMotion = reducedMotion;
      config.paused = reducedMotion;
      actor.source.getLevel = () => level;
      tick(actor, now);
      animation.effect.setKeyframes([properties]);
    },
    destroy() {
      animation.cancel();
    },
  };
}
function tick(a, n) {
  const be = {
    level: 0,
    bands: [0, 0, 0],
  };
  const { el: r, config: t, source: s, s: o } = a,
    i = t.paused;
  if (i && a.paintedConfig === t) return;
  const u = i ? 0 : o.lastTs ? Math.min(0.05, (n - o.lastTs) / 1e3) : 1 / 60;
  o.lastTs = n;
  o.t += u;
  const l = o.t;
  if (!i) {
    const f = s.getLevel ? Sa(s.getLevel()) : 0;
    be.level = f;
    be.bands[0] = f;
    be.bands[1] = f * (0.72 + 0.28 * Math.sin(l * 9.1));
    be.bands[2] = f * (0.6 + 0.4 * Math.sin(l * 13.7 + 2));
  }
  const p = pa(be.level, t.threshold);
  o.level = Ge(o.level, p, u, t.attack, t.release);
  for (let f = 0; f < 3; f++) {
    const B = pa(be.bands[f], t.threshold * 0.6);
    o.bands[f] = Ge(o.bands[f], B, u, t.attack, t.release * 1.15);
  }
  const b = Ka * t.lobeSpacing;
  if (t.processing && o.scanA < 1e-3 && o.scanT === 0) {
    o.scanT = Math.max(0.05, t.processingDuration) / 2;
  }
  const d = Math.max(0.05, t.processingEase);
  o.scanA = Ge(o.scanA, t.processing ? 1 : 0, u, d * 0.9, d * 0.8);
  if (t.processing) {
    o.scanT += u;
  } else {
    if (o.scanA < 1e-3) {
      o.scanT = 0;
    }
  }
  const h = o.scanA * o.scanA * (3 - 2 * o.scanA),
    T = r.clientWidth,
    O = r.clientHeight,
    L = (b / 2) * t.processingTravel,
    _ = o.scanT / Math.max(0.05, t.processingDuration),
    G = Math.floor(_),
    U = _ - G,
    E = Math.max(1, t.processingCurve),
    D = U < 0.5 ? 0.5 * Math.pow(2 * U, E) : 1 - 0.5 * Math.pow(2 - 2 * U, E),
    C = t.reducedMotion ? 0 : G % 2 === 0 ? 2 * D - 1 : 1 - 2 * D,
    z = h * L * C,
    g = 1 - h * 0.6,
    H = 1 - h * 0.45,
    Q = 1 + h * 0.3 * (1 - C * C),
    le = t.reducedMotion ? 0.5 : 0.5 + 0.5 * Math.sin((Ma * l) / t.breatheDuration),
    K = o.level + (1 - o.level) * t.idle * le,
    W = Math.max(0, Math.min(1, (h - 0.25) / 0.75)),
    R = W * W * (3 - 2 * W),
    I = Math.max(K, t.processingLevel * R),
    P = 0.15 + 0.85 * I,
    v = 0.5 + t.reach * I,
    k = (0.85 + t.spread * I) * Q;
  if (t.flow !== 0 && !t.reducedMotion) {
    o.phase = (((o.phase + t.flow * I * u) % b) + b) % b;
  }
  writeProperty(`--vb-level-${t.id}`, o.level.toFixed(3));
  writeProperty(`--vb-cx-${t.id}`, `${z.toFixed(1)}px`);
  writeProperty(`--vb-mw-${t.id}`, H.toFixed(3));
  const w = t.bend * I;
  writeProperty(`--vb-bh-${t.id}`, `${Math.max(0, w).toFixed(1)}px`);
  const S = t.bend > 0 ? Math.min(1, w / t.bend) : 0;
  writeProperty(`--vb-bendA-${t.id}`, S.toFixed(3));
  const x = {
      cx: z,
      w: k,
      h: v,
      mw: H,
      lift: w,
      strength: S,
      level: o.level,
      corner: h,
    },
    y = T / 2 + z * k,
    oe = 30 * t.scale * k,
    xe = Ta(t.radius, T, O),
    re = h * t.cornerFollow;
  writeProperty(`--vb-cy-${t.id}`, `${(-gt(y, T, xe, oe * 1.4) * re).toFixed(1)}px`);
  o.warp = Ge(o.warp, t.processing ? 0 : 1, u, hn, dn);
  const ye = o.warp,
    V = a.displace != null && ye < bn;
  if (
    (V !== a.warpOff &&
      ((a.warpOff = V),
      V ? r.setAttribute("data-voice-warp", "off") : r.removeAttribute("data-voice-warp")),
    T && O && (a.ctx || a.displace))
  ) {
    const f = xn(t, x, T, O);
    if ((a.displace && !V) || t.coreLight > 0) {
      yn(r, t.id, f, T, O);
    }
    if (a.filter && !V && un) {
      Mn(a, f, O);
    }
    if (a.ctx) {
      Sn(a, x, f);
    }
  }
  if (a.displace && !V) {
    const f = t.reducedMotion ? 0 : t.distortion * 120 * t.scale * (0.15 + 0.85 * I) * ye;
    a.displace.scale.baseVal = f;
    if (a.noiseShift) {
      a.noiseShift.dx.baseVal = 8 * t.scale * Math.sin(l * 0.9);
      a.noiseShift.dy.baseVal = 4 * t.scale * Math.sin(l * 0.6 + 1.3);
    }
  }
  writeProperty(`--vb-glow-${t.id}`, P.toFixed(3));
  writeProperty(`--vb-h-${t.id}`, v.toFixed(3));
  writeProperty(`--vb-w-${t.id}`, k.toFixed(3));
  for (let f = 0; f < we.length; f++) {
    const B = we[f],
      j = sn(B.x * t.lobeSpacing + o.phase, b),
      Z = t.bands ? 0.6 + 0.7 * o.bands[B.band] : 1;
    writeProperty(`--vb-x${f}-${t.id}`, `${(j * g).toFixed(1)}px`);
    writeProperty(`--vb-l${f}-${t.id}`, (Z * cn(j, b)).toFixed(3));
    const ge = T / 2 + (z + j * g) * k;
    writeProperty(`--vb-y${f}-${t.id}`, `${(-gt(ge, T, xe, oe) * re).toFixed(1)}px`);
  }
  const Me =
    t.staticColors || t.reducedMotion || t.hueRange === 0
      ? 0
      : -t.hueRange + 2 * t.hueRange * Tn(l / t.hueDuration);
  writeProperty(`--vb-hue-${t.id}`, `${Me.toFixed(2)}deg`);
  a.paintedConfig = t;
}
