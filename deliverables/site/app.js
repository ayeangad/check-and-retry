(function () {
  'use strict';

  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const $ = (id) => document.getElementById(id);

  /* ---------- Theme toggle: circular wipe from the click point ---------- */
  const root = document.documentElement;
  const themeBtn = $('theme');
  function syncThemeLabel() {
    const dark = root.getAttribute('data-theme') === 'dark';
    themeBtn.setAttribute('aria-label', dark ? 'Switch to light theme' : 'Switch to dark theme');
  }
  syncThemeLabel();
  themeBtn.addEventListener('click', (e) => {
    const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    const apply = () => {
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (_) {}
      syncThemeLabel();
    };
    if (!document.startViewTransition || reduce) return apply();
    root.style.setProperty('--click-x', e.clientX + 'px');
    root.style.setProperty('--click-y', e.clientY + 'px');
    document.startViewTransition(apply);
  });

  /* ---------- Replay data: Exhibit 1, DeepSeek V4.1 Flash, run 3 (verbatim from transcripts) ---------- */
  const GEN = 'Load the reference photo, scale to 1920×1080, img2img at denoise 0.62, decode';
  const V1 = [
    { id: '1–8', t: GEN },
    { id: '9', t: 'LoadImage  X00_exhibit1_input2_logo.png' },
    { id: '10', t: 'ImageScale  logo → 420×168, lanczos', hot: true },
    { id: '11', t: 'ImageCompositeMasked  x=80  y=70', hot: true },
    { id: '12', t: 'SaveImage' },
  ];
  const V2_SAME = [
    { id: '1–8', t: GEN },
    { id: '9', t: 'LoadImage  X00_exhibit1_input2_logo.png' },
    { id: '10', t: 'ImageScale  logo → 420×168, lanczos', gone: true },
    { id: '10', t: 'ImageCompositeMasked  x=80  y=70  (logo pasted as supplied)', hot: true },
    { id: '11', t: 'SaveImage' },
  ];
  const V2_MOVED = [
    { id: '1–8', t: GEN },
    { id: '9', t: 'LoadImage  X00_exhibit1_input2_logo.png' },
    { id: '10', t: 'ImageScale  logo → 420×168, lanczos', gone: true },
    { id: '10', t: 'ImageCompositeMasked  x=32  y=32  (logo pasted as supplied)', hot: true },
    { id: '11', t: 'SaveImage' },
  ];
  const STRETCHED = { x: 80, y: 70, w: 420, h: 168 };
  const EXACT_80 = { x: 80, y: 70, w: 300, h: 70 };
  const EXACT_32 = { x: 32, y: 32, w: 300, h: 70 };

  const FB_OUTPUT = 'The workflow ran. Checking the delivered image(s) against the brief:\n- logo_exact: the supplied logo X00_exhibit1_input2_logo.png does not appear unaltered (same pixels, same size) in the delivered image.\nNot delivered. Fix these and submit again.';
  const FB_RICH = 'The workflow ran. Checking the delivered image(s) against the brief:\n- logo_exact: the supplied logo X00_exhibit1_input2_logo.png does not appear unaltered (same pixels, same size) in the delivered image. The supplied logo is 300x70 pixels; on the required 1920x1080 canvas, paste it unscaled with its top-left at x=32, y=32.\nNot delivered. Fix these and submit again.';
  const FB_PLAN = 'ComfyUI validation: OK, but the workflow does not meet the brief:\nBrief contract: 2 requirement(s) violated:\n- logo_exact: [node 12] ImageScale (node 10) resamples the image from 300x70 to 420x168, which rescales the logo\'s pixels\n  fix: load the logo with LoadImage and paste it with ImageCompositeMasked (resize_source=false, no mask) AFTER all generation and resizing, directly before SaveImage\n- logo_position: [node 12] logo not reproduced exactly, so its position cannot be checked\n  fix: see logo_exact\nNot delivered. Fix these and submit again.';

  const SUBMIT = { label: 'Submit', title: 'The agent submits its first workflow', what: 'Shared by all four versions. The workflow is valid ComfyUI: every node exists and every edge type-checks. But node 10 resamples the logo before it is pasted.', nodes: V1, logo: STRETCHED, state: 'workflow v1', gen: 0, time: null };

  const ARMS = [
    {
      key: 'validate', name: 'Validation only', ok: false, steps: [
        SUBMIT,
        { label: 'Check', title: 'ComfyUI validates it', what: 'Validation answers one question: will this run? It will. Nothing in the check knows what the brief asked for.', nodes: V1, logo: STRETCHED, fbSrc: 'Tool reply', fb: 'Accepted.', state: 'workflow v1, accepted', gen: 0, time: '0 ms' },
        { label: 'Deliver', title: 'It renders and ships', what: 'One paid render. The delivered PNG is the right size, but the logo is a resampled 420×168 copy: the brief is not met.', nodes: V1, logo: STRETCHED, state: 'delivered', gen: 1, time: '0 ms', done: true },
      ],
    },
    {
      key: 'output', name: 'Check the output', ok: true, steps: [
        SUBMIT,
        { label: 'Check', title: 'It renders, then inspects the image', what: 'A paid render, then a pixel check against the brief. The check can say what is wrong with the image, not where in the graph it came from.', nodes: V1, logo: STRETCHED, fbSrc: 'Tool reply', fb: FB_OUTPUT, state: 'workflow v1, rejected', gen: 1, time: '1.0 s' },
        { label: 'Retry', title: 'The agent drops the resize', what: 'It finds the culprit itself this time: node 10 goes, and the logo is pasted as supplied.', nodes: V2_SAME, logo: EXACT_80, state: 'workflow v2', gen: 1, time: '1.0 s' },
        { label: 'Check', title: 'It renders and inspects again', what: 'A second paid render. The logo is now pixel-exact and in the upper-left zone.', nodes: V2_SAME, logo: EXACT_80, fbSrc: 'Tool reply', fb: 'Accepted.', state: 'workflow v2, accepted', gen: 2, time: '2.0 s' },
        { label: 'Deliver', title: 'Brief met, after two renders', what: 'The accepted render is the deliverable. On this brief the plain output check was enough; across 111 runs it rescued 27%.', nodes: V2_SAME, logo: EXACT_80, state: 'delivered', gen: 2, time: '2.0 s', done: true },
      ],
    },
    {
      key: 'rich', name: 'Check the output, with the fix', ok: true, steps: [
        SUBMIT,
        { label: 'Check', title: 'It renders, then inspects the image', what: 'Same render and pixel check, but the reply also carries the logo’s real size and where to paste it: the same facts the plan check gives.', nodes: V1, logo: STRETCHED, fbSrc: 'Tool reply', fb: FB_RICH, state: 'workflow v1, rejected', gen: 1, time: '0.9 s' },
        { label: 'Retry', title: 'The agent follows the fix', what: 'Node 10 goes and the logo moves to the coordinates it was given.', nodes: V2_MOVED, logo: EXACT_32, state: 'workflow v2', gen: 1, time: '0.9 s' },
        { label: 'Check', title: 'It renders and inspects again', what: 'A second paid render, accepted.', nodes: V2_MOVED, logo: EXACT_32, fbSrc: 'Tool reply', fb: 'Accepted.', state: 'workflow v2, accepted', gen: 2, time: '1.8 s' },
        { label: 'Deliver', title: 'Brief met, after two renders', what: 'Across 111 runs this version met the brief 98 times, exactly as often as the plan check, at twice the renders.', nodes: V2_MOVED, logo: EXACT_32, state: 'delivered', gen: 2, time: '1.8 s', done: true },
      ],
    },
    {
      key: 'plan', name: 'Check the plan', ok: true, steps: [
        SUBMIT,
        { label: 'Check', title: 'It reads the graph, without rendering', what: 'The brief contract traces sizes and logo pixels through the graph before anything runs. It names the node that breaks the brief and how to fix it.', nodes: V1, logo: STRETCHED, fbSrc: 'Tool reply', fb: FB_PLAN, state: 'workflow v1, rejected before rendering', gen: 0, time: '0.3 ms' },
        { label: 'Retry', title: 'The agent drops the resize', what: 'Node 10 goes; the logo is pasted as supplied, after all generation and resizing.', nodes: V2_SAME, logo: EXACT_80, state: 'workflow v2', gen: 0, time: '0.3 ms' },
        { label: 'Check', title: 'The graph passes the contract', what: 'Still no render: the contract can see that the logo reaches SaveImage untouched and inside the upper-left zone.', nodes: V2_SAME, logo: EXACT_80, fbSrc: 'Tool reply', fb: 'Accepted.', state: 'workflow v2, accepted', gen: 0, time: '0.6 ms' },
        { label: 'Deliver', title: 'Brief met, after one render', what: 'The only render is the deliverable. Across 111 runs: 98 briefs met, 104 renders.', nodes: V2_SAME, logo: EXACT_80, state: 'delivered', gen: 1, time: '0.6 ms', done: true },
      ],
    },
  ];

  /* ---------- Reference composition (synthetic stand-in, scaled 1.25× and centre-cropped) ---------- */
  const REFS = [[62, 35, 410, 648], [1105, 360, 1415, 622], [928, 625, 1638, 1080], [332, 830, 452, 1080], [455, 820, 1310, 1080]];
  const NS = 'http://www.w3.org/2000/svg';
  const refs = $('refs');
  REFS.forEach(([x0, y0, x1, y1]) => {
    const r = document.createElementNS(NS, 'rect');
    r.setAttribute('class', 'ref');
    r.setAttribute('x', x0); r.setAttribute('y', y0);
    r.setAttribute('width', x1 - x0); r.setAttribute('height', y1 - y0);
    refs.appendChild(r);
  });

  /* ---------- Icons (authored, one stroke weight) ---------- */
  const ICON = {
    pass: '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="8.25" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M6.2 10.3l2.5 2.5 5.1-5.4" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    fail: '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="8.25" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M7 7l6 6M13 7l-6 6" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
  };

  /* ---------- Replay state ---------- */
  let arm = ARMS[3];
  let step = 0;
  const logoImg = $('logo-img'), logoBox = $('logo-box'), logoLabel = $('logo-label'), stamp = $('stamp');
  let cur = { ...STRETCHED };
  let anim = null;

  function setLogo(r) {
    [logoImg, logoBox].forEach((el) => {
      el.setAttribute('x', r.x); el.setAttribute('y', r.y);
      el.setAttribute('width', r.w); el.setAttribute('height', r.h);
    });
    logoLabel.setAttribute('x', r.x);
    logoLabel.setAttribute('y', r.y + r.h + (r.y + r.h + 36 > 255 && r.y + r.h < 270 ? 62 : 36));
  }
  function moveLogo(to) {
    cancelAnimationFrame(anim);
    const from = { ...cur };
    const label = `${to.w}×${to.h} at (${to.x}, ${to.y})`;
    logoLabel.textContent = label;
    if (reduce) { cur = { ...to }; setLogo(cur); return; }
    const t0 = performance.now(), dur = 700;
    const ease = (t) => 1 - Math.pow(1 - t, 4);
    const tick = (now) => {
      const k = ease(Math.min(1, (now - t0) / dur));
      cur = { x: from.x + (to.x - from.x) * k, y: from.y + (to.y - from.y) * k, w: from.w + (to.w - from.w) * k, h: from.h + (to.h - from.h) * k };
      setLogo(cur);
      if (k < 1) anim = requestAnimationFrame(tick);
    };
    anim = requestAnimationFrame(tick);
  }

  const armsEl = $('arms');
  ARMS.forEach((a) => {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'arm-btn'; b.setAttribute('role', 'radio');
    b.textContent = a.name; b.dataset.key = a.key;
    b.addEventListener('click', () => { arm = a; step = 0; render(); });
    b.addEventListener('keydown', (e) => {
      const i = ARMS.indexOf(a);
      let j = null;
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') j = (i + 1) % ARMS.length;
      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') j = (i - 1 + ARMS.length) % ARMS.length;
      if (j !== null) { e.preventDefault(); arm = ARMS[j]; step = 0; render(); armsEl.querySelectorAll('.arm-btn')[j].focus(); }
    });
    armsEl.appendChild(b);
  });

  const stepsEl = $('steps');
  for (let i = 0; i < 5; i++) {
    const li = document.createElement('li');
    const b = document.createElement('button');
    b.type = 'button';
    b.addEventListener('click', () => { step = i; render(); });
    li.appendChild(b); stepsEl.appendChild(li);
  }

  function render() {
    armsEl.querySelectorAll('.arm-btn').forEach((b) => {
      const on = b.dataset.key === arm.key;
      b.setAttribute('aria-checked', on); b.tabIndex = on ? 0 : -1;
    });
    const s = arm.steps[step];
    [...stepsEl.children].forEach((li, i) => {
      const st = arm.steps[i];
      li.hidden = !st;
      if (!st) return;
      const b = li.firstChild;
      b.textContent = st.label;
      b.classList.toggle('done', i < step);
      if (i === step) b.setAttribute('aria-current', 'step'); else b.removeAttribute('aria-current');
    });
    $('p-title').textContent = s.title;
    $('p-what').textContent = s.what;
    const nodes = $('p-nodes'); nodes.innerHTML = '';
    s.nodes.forEach((n) => {
      const li = document.createElement('li');
      if (n.hot) li.className = 'hot';
      if (n.gone) li.className = 'gone';
      li.innerHTML = `<span class="id"></span><span></span>`;
      li.firstChild.textContent = n.id; li.lastChild.textContent = n.t;
      nodes.appendChild(li);
    });
    const fb = $('p-feedback');
    if (s.fb) { fb.hidden = false; fb.innerHTML = '<span class="src"></span><span class="txt"></span>'; fb.firstChild.textContent = s.fbSrc + ', verbatim'; fb.lastChild.textContent = s.fb; }
    else fb.hidden = true;
    moveLogo(s.logo);
    $('canvas-state').textContent = s.state;
    $('l-gen').textContent = s.gen;
    $('l-time').innerHTML = s.time ? s.time.replace(/ (ms|s)$/, ' <small>$1</small>') : '<small>—</small>';
    const res = $('l-result');
    if (s.done) {
      res.innerHTML = `<span class="verdict ${arm.ok ? 'pass' : 'fail'}">${arm.ok ? ICON.pass : ICON.fail}${arm.ok ? 'Yes' : 'No'}</span>`;
      stamp.textContent = arm.ok ? 'logo: exact pixels, upper-left' : 'logo: resampled, brief not met';
      stamp.style.fill = arm.ok ? 'var(--pass)' : 'var(--fail)';
    } else {
      res.innerHTML = '<span class="verdict pending"><small>not yet</small></span>';
      stamp.textContent = '';
    }
    const last = step === arm.steps.length - 1;
    $('next').disabled = last;
    $('next').textContent = last ? 'Delivered' : `Next: ${arm.steps[step + 1].label.toLowerCase()}`;
  }
  const q = new URLSearchParams(location.search);
  const qa = ARMS.find((a) => a.key === q.get('arm'));
  if (qa) { arm = qa; step = Math.min(Math.max(0, (+q.get('step') || 1) - 1), qa.steps.length - 1); }
  $('next').addEventListener('click', () => { if (step < arm.steps.length - 1) { step++; render(); } });
  $('restart').addEventListener('click', () => { step = 0; render(); });
  render();

  /* ---------- Charts (n = 111 per arm; D-B, logo briefs, 3 runs) ---------- */
  const DATA = [
    { name: 'Validation only', k: 10, n: 111, p: 9.0, lo: 5.0, hi: 15.8, gen: 0.93, tok: 10587, t: '0 ms' },
    { name: 'Check the output', k: 30, n: 111, p: 27.0, lo: 19.6, hi: 36.0, gen: 1.95, tok: 34457, t: '1.6 s' },
    { name: 'Check the output, with the fix', k: 98, n: 111, p: 88.3, lo: 81.0, hi: 93.0, gen: 1.95, tok: 17480, t: '1.5 s' },
    { name: 'Check the plan', k: 98, n: 111, p: 88.3, lo: 81.0, hi: 93.0, gen: 0.94, tok: 14431, t: '0.8 ms', hl: true },
  ];
  const tip = $('tip');
  function showTip(e, html) {
    tip.innerHTML = html; tip.classList.add('on');
    const r = tip.getBoundingClientRect();
    let x = e.clientX + 14, y = e.clientY + 14;
    if (x + r.width > innerWidth - 8) x = e.clientX - r.width - 14;
    if (y + r.height > innerHeight - 8) y = e.clientY - r.height - 14;
    tip.style.left = x + 'px'; tip.style.top = y + 'px';
  }
  const hideTip = () => tip.classList.remove('on');
  const el = (tag, attrs, parent) => {
    const n = document.createElementNS(NS, tag);
    for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(n);
    return n;
  };

  function rowChart(host, { max, ticks, fmt, value, ci, tipFor }) {
    host.querySelector('svg')?.remove();
    const W = Math.max(300, Math.round(host.clientWidth)), rowH = 46, top = 8;
    const labelW = W < 460 ? Math.round(W * 0.42) : 230;
    const H = top + DATA.length * rowH + 30, x0 = labelW, x1 = W - 56;
    const sx = (v) => x0 + (v / max) * (x1 - x0);
    const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': host.querySelector('h3').textContent });
    const g = el('g', { class: 'grid axis' }, svg);
    ticks.forEach((t) => {
      el('line', { x1: sx(t), x2: sx(t), y1: top, y2: H - 26 }, g);
      const tx = el('text', { x: sx(t), y: H - 8, 'text-anchor': 'middle' }, g); tx.textContent = fmt(t);
    });
    DATA.forEach((d, i) => {
      const cy = top + i * rowH + rowH / 2;
      const row = el('g', { class: 'row' + (d.hl ? ' hl' : '') }, svg);
      const lab = el('text', { class: 'row-lab', x: 0, y: cy + 4 }, row); lab.textContent = d.name;
      if (ci) {
        el('line', { class: 'ci', x1: sx(d.lo), x2: sx(d.hi), y1: cy, y2: cy }, row);
        el('circle', { class: 'dot', cx: sx(d.p), cy, r: 6 }, row);
        const v = el('text', { class: 'val', x: sx(d.hi) + 10, y: cy + 4 }, row); v.textContent = `${Math.round(d.p)}%`;
      } else {
        const w = Math.max(4, sx(value(d)) - x0);
        el('rect', { class: 'bar', x: x0, y: cy - 7, width: w, height: 14, rx: 3 }, row);
        const v = el('text', { class: 'val', x: x0 + w + 10, y: cy + 4 }, row); v.textContent = value(d).toFixed(2);
      }
      const hit = el('rect', { class: 'hit', x: 0, y: cy - rowH / 2, width: W, height: rowH }, row);
      hit.addEventListener('mousemove', (e) => showTip(e, tipFor(d)));
      hit.addEventListener('mouseleave', hideTip);
    });
    host.appendChild(svg);
  }
  function drawCharts() {
    rowChart($('chart-pass'), {
      max: 100, ticks: [0, 25, 50, 75, 100], fmt: (t) => t + '%', ci: true,
      tipFor: (d) => `${d.name}<br>${d.k} of ${d.n} runs met the brief<br>${d.p.toFixed(1)}%, 95% CI ${d.lo}–${d.hi}%`,
    });
    rowChart($('chart-gen'), {
      max: 2, ticks: [0, 1, 2], fmt: (t) => String(t), value: (d) => d.gen,
      tipFor: (d) => `${d.name}<br>${d.gen.toFixed(2)} renders per run<br>${Math.round(d.gen * d.n)} renders in ${d.n} runs`,
    });
  }
  drawCharts();
  let rz;
  window.addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(drawCharts, 120); });
  const tb = $('table-body');
  DATA.forEach((d) => {
    const tr = document.createElement('tr');
    [d.name, `${d.k} / ${d.n} (${d.p.toFixed(1)}%)`, `${d.lo}–${d.hi}%`, d.gen.toFixed(2), d.tok.toLocaleString('en-US'), d.t].forEach((v, i) => {
      const td = document.createElement('td'); td.textContent = v; if (i) td.className = 'n'; tr.appendChild(td);
    });
    tb.appendChild(tr);
  });
})();
