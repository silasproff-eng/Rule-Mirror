const TEMPLATE = document.createElement("template");
TEMPLATE.innerHTML = `
  <style>
    :host {
      display: inline-block;
      width: var(--rm-size, 88px);
      height: var(--rm-size, 88px);
      contain: layout paint style;
      user-select: none;
      -webkit-user-select: none;
      touch-action: manipulation;
    }

    canvas {
      display: block;
      width: 100%;
      height: 100%;
    }
  </style>
  <canvas part="canvas" aria-label="RuleMirror assistant mascot"></canvas>
`;

const clamp = (v, min, max) => Math.max(min, Math.min(max, v));
const lerp = (a, b, t) => a + (b - a) * t;
const easeOutCubic = t => 1 - Math.pow(1 - t, 3);

export class RuleMirrorMascot extends HTMLElement {
  static get observedAttributes() {
    return ["size", "theme", "green", "state"];
  }

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.appendChild(TEMPLATE.content.cloneNode(true));

    this.canvas = this.shadowRoot.querySelector("canvas");
    this.ctx = this.canvas.getContext("2d", { alpha: true });

    this.green = "#2FB36F";
    this.theme = "light";
    this.state = "idle";

    this.particles = [];
    this.pointer = { x: 0, y: 0, tx: 0, ty: 0, inside: false };
    this.eye = { x: 0, y: 0, vx: 0, vy: 0 };
    this.scrollVelocity = 0;
    this.lastScroll = 0;
    this.lastFrame = performance.now();
    this.time = 0;
    this.breathCycle = 0;
    this.nextBreathOffset = 1;
    this.breathOffset = new Map();

    this.speaking = false;
    this.speakUntil = 0;
    this.mouthPhase = 0;
    this.ripples = [];
    this.clickPulse = 0;
    this.cursorBodyX = 0;
    this.cursorBodyY = 0;
    this.nextBlink = 2 + Math.random() * 2;
    this.lastBlink = 0;
    this.bodyCursorX = 0;
    this.bodyCursorY = 0;
    this.statePulse = 0;

    this.reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    this._resizeObserver = new ResizeObserver(() => this.resize());
    this._raf = 0;

    this.onPointerMove = this.onPointerMove.bind(this);
    this.onPointerLeave = this.onPointerLeave.bind(this);
    this.onWindowPointerMove = this.onWindowPointerMove.bind(this);
    this.onWheel = this.onWheel.bind(this);
    this.onClick = this.onClick.bind(this);
    this.onWindowClick = this.onWindowClick.bind(this);
    this.frame = this.frame.bind(this);
  }

  connectedCallback() {
    this.applyAttributes();
    this._resizeObserver.observe(this);
    if (!this.reducedMotion) {
      window.addEventListener("pointermove", this.onWindowPointerMove, { passive: true });
      window.addEventListener("wheel", this.onWheel, { passive: true });
      window.addEventListener("click", this.onWindowClick, { passive: true });
      this.addEventListener("pointermove", this.onPointerMove, { passive: true });
      this.addEventListener("pointerleave", this.onPointerLeave, { passive: true });
      this.addEventListener("click", this.onClick);
    }
    this.resize();
    if (!this.reducedMotion) this._raf = requestAnimationFrame(this.frame);
  }

  disconnectedCallback() {
    this._resizeObserver.disconnect();
    window.removeEventListener("pointermove", this.onWindowPointerMove);
    window.removeEventListener("wheel", this.onWheel);
    window.removeEventListener("click", this.onWindowClick);
    this.removeEventListener("pointermove", this.onPointerMove);
    this.removeEventListener("pointerleave", this.onPointerLeave);
    this.removeEventListener("click", this.onClick);
    cancelAnimationFrame(this._raf);
  }

  onWindowClick(event) {
    if (!this.contains(event.target)) {
      this.ripple(0, 0);
      this.clickPulse = 1;
    }
  }

  attributeChangedCallback() {
    if (this.isConnected) {
      this.applyAttributes();
      this.resize();
    }
  }

  applyAttributes() {
    const size = Number(this.getAttribute("size")) || 88;
    this.style.setProperty("--rm-size", `${size}px`);

    const theme = this.getAttribute("theme");
    if (theme === "dark" || theme === "green" || theme === "light") {
      this.theme = theme;
    }

    const green = this.getAttribute("green");
    if (green) this.green = green;

    const state = this.getAttribute("state");
    if (state) this.setState(state);
  }

  resize() {
    const rect = this.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const width = Math.max(1, Math.round(rect.width * dpr));
    const height = Math.max(1, Math.round(rect.height * dpr));

    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
      this.dpr = dpr;
      this.width = rect.width;
      this.height = rect.height;
      this.generateParticles();
    }
    if (this.reducedMotion) this.draw();
  }

  generateParticles() {
    const size = Math.min(this.width || 88, this.height || 88);
    const radius = size * 0.43;
    const spacing = size / 13.4;
    const rowStep = spacing * Math.sqrt(3) / 2;

    this.particles = [];
    let row = 0;

    for (let y = -radius; y <= radius; y += rowStep) {
      const offsetX = (row % 2) * spacing * 0.5;

      for (let x = -radius; x <= radius; x += spacing) {
        const px = x + offsetX;
        const dist = Math.hypot(px, y);
        if (dist <= radius) {
          const n = dist / radius;
          const edge = clamp(1 - n, 0, 1);
          const baseRadius = spacing * (0.12 + 0.34 * Math.pow(edge, 0.74));
          const opacity = 0.14 + 0.86 * Math.pow(edge, 0.72);

          this.particles.push({
            x: px,
            y,
            dist,
            n,
            baseRadius,
            opacity,
            phase: Math.random() * Math.PI * 2,
            speed: 0.62 + Math.random() * 0.55,
            jitter: 0.75 + Math.random() * 0.5,
            breathOffset: 1
          });
        }
      }
      row += 1;
    }
  }

  onWindowPointerMove(event) {
    const rect = this.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const scale = Math.max(rect.width, rect.height) * 2.2;

    this.pointer.tx = clamp((event.clientX - cx) / scale, -1, 1);
    this.pointer.ty = clamp((event.clientY - cy) / scale, -1, 1);
  }

  onPointerMove(event) {
    const rect = this.getBoundingClientRect();
    this.pointer.x = event.clientX - rect.left - rect.width / 2;
    this.pointer.y = event.clientY - rect.top - rect.height / 2;
    this.pointer.inside = true;
  }

  onPointerLeave() {
    this.pointer.inside = false;
  }

  onWheel(event) {
    this.scrollVelocity = clamp(this.scrollVelocity + event.deltaY * 0.0007, -1.2, 1.2);
    this.lastScroll = performance.now();
  }

  onClick(event) {
    const rect = this.getBoundingClientRect();
    const x = event.clientX - rect.left - rect.width / 2;
    const y = event.clientY - rect.top - rect.height / 2;
    this.ripple(x, y);
    this.clickPulse = 1;
    this.dispatchEvent(new CustomEvent("rulemirror-click", {
      bubbles: true,
      composed: true
    }));
  }

  ripple(x = 0, y = 0) {
    this.ripples.push({ x, y, age: 0, duration: 0.68 });
  }

  setTheme(theme) {
    if (!["light", "green", "dark"].includes(theme)) return;
    this.theme = theme;
    this.setAttribute("theme", theme);
  }

  setState(nextState) {
    const allowed = ["idle", "thinking", "speaking", "success", "warning", "error"];
    if (!allowed.includes(nextState)) return;

    this.state = nextState;
    this.statePulse = 1;

    if (nextState === "speaking") {
      this.speaking = true;
    } else if (this.speaking && nextState !== "speaking") {
      this.speaking = false;
    }

    if (nextState === "success") this.ripple(0, 0);
    if (nextState === "error") this.clickPulse = 0.9;

    this.dispatchEvent(new CustomEvent("rulemirror-state", {
      detail: { state: nextState },
      bubbles: true,
      composed: true
    }));
  }

  speak(active = true, durationMs = 0) {
    this.speaking = active;
    if (active) {
      this.state = "speaking";
      this.speakUntil = durationMs > 0 ? performance.now() + durationMs : 0;
    } else {
      this.speakUntil = 0;
      if (this.state === "speaking") this.state = "idle";
    }
  }

  pulse() {
    this.ripple(0, 0);
  }

  reset() {
    this.state = "idle";
    this.speaking = false;
    this.speakUntil = 0;
    this.scrollVelocity = 0;
    this.ripples = [];
    this.clickPulse = 0;
    this.cursorBodyX = 0;
    this.cursorBodyY = 0;
    this.nextBlink = 2 + Math.random() * 2;
    this.lastBlink = 0;
    this.bodyCursorX = 0;
    this.bodyCursorY = 0;
    this.statePulse = 0;
  }

  colors() {
    if (this.theme === "green") {
      return {
        particle: "#FFFFFF",
        face: "#FFFFFF",
        mouthOpen: "#131313",
        teeth: "#FFFFFF",
        tongue: "#F18DA3"
      };
    }

    if (this.theme === "dark") {
      return {
        particle: "#FFFFFF",
        face: "#FFFFFF",
        mouthOpen: "#0F0F0F",
        teeth: "#FFFFFF",
        tongue: "#F18DA3"
      };
    }

    return {
      particle: this.green,
      face: "#111111",
      mouthOpen: "#111111",
      teeth: "#FFFFFF",
      tongue: "#F18DA3"
    };
  }

  update(dt, now) {
    this.time += dt;

    if (!this.breathCycleTime || this.time > this.breathCycleTime) {
      this.breathCycleTime = this.time + 2.4 + Math.random() * 1.2;
      for (const p of this.particles) {
        p.breathOffset = Math.random() < 0.35
          ? 1.02 + Math.random() * 0.04
          : 1;
      }
    }

    const breathNow = Math.floor(this.time / 2.8);
    if (breathNow !== this.breathCycle) {
      this.breathCycle = breathNow;
      this.nextBreathOffset = 0.96 + Math.random() * 0.08;
      for (const p of this.particles) {
        if (Math.random() < 0.22) {
          p.breathBoost = 1.02 + Math.random() * 0.04;
        } else {
          p.breathBoost = 1;
        }
      }
    }

    if (this.speakUntil && now >= this.speakUntil) {
      this.speak(false);
    }

    if (!this.reducedMotion) {
      const spring = 23;
      const damping = 0.76;
      this.eye.vx += (this.pointer.tx - this.eye.x) * spring * dt;
      this.eye.vy += (this.pointer.ty - this.eye.y) * spring * dt;
      this.eye.vx *= Math.pow(damping, dt * 60);
      this.eye.vy *= Math.pow(damping, dt * 60);
      this.eye.x += this.eye.vx * dt;
      this.eye.y += this.eye.vy * dt;
    } else {
      this.eye.x = this.pointer.tx * 0.3;
      this.eye.y = this.pointer.ty * 0.3;
    }

    const bodyTargetX = this.pointer.tx * 4;
    const bodyTargetY = this.pointer.ty * 4;
    this.bodyCursorX = lerp(this.bodyCursorX, bodyTargetX, 0.08);
    this.bodyCursorY = lerp(this.bodyCursorY, bodyTargetY, 0.08);

    this.cursorBodyX = lerp(
      this.cursorBodyX,
      this.pointer.tx * 12,
      0.08
    );
    this.cursorBodyY = lerp(
      this.cursorBodyY,
      this.pointer.ty * 12,
      0.08
    );

    this.scrollVelocity *= Math.pow(0.86, dt * 60);
    this.clickPulse *= Math.pow(0.82, dt * 60);
    this.statePulse *= Math.pow(0.9, dt * 60);

    for (const ripple of this.ripples) ripple.age += dt;
    this.ripples = this.ripples.filter(r => r.age < r.duration);

    if (this.speaking && !this.reducedMotion) {
      this.mouthPhase += dt * 8.8;
    } else {
      this.mouthPhase = lerp(this.mouthPhase, 0, 0.15);
    }
  }

  draw() {
    const ctx = this.ctx;
    const dpr = this.dpr || 1;
    const w = this.width || 88;
    const h = this.height || 88;
    const size = Math.min(w, h);
    const cx = w / 2;
    const cy = h / 2;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const colors = this.colors();
    const globalBreath = this.reducedMotion
      ? 1
      : 1 + Math.sin(this.time * 1.12) * 0.045 * this.nextBreathOffset;

    let stateScale = 1;
    let stateWobble = 0;

    if (!this.reducedMotion) {
      if (this.state === "thinking") {
        stateScale += Math.sin(this.time * 3.1) * 0.012;
        stateWobble = Math.sin(this.time * 2.0) * 0.008;
      } else if (this.state === "success") {
        stateScale += this.statePulse * 0.024;
      } else if (this.state === "warning") {
        stateWobble = Math.sin(this.time * 4.5) * 0.012;
      } else if (this.state === "error") {
        stateWobble = Math.sin(this.time * 20) * this.statePulse * 0.025;
      }
    }

    const scrollStretch = clamp(this.scrollVelocity, -1, 1) * 0.035;
    const sx = globalBreath * stateScale * (1 - Math.abs(scrollStretch) * 0.35);
    const sy = globalBreath * stateScale * (1 + Math.abs(scrollStretch));

    ctx.save();
    ctx.translate(cx + this.bodyCursorX, cy + this.bodyCursorY);
    ctx.rotate(stateWobble);

    for (const p of this.particles) {
      const localBreath = this.reducedMotion
        ? 1
        : 1 + Math.sin(this.time * p.speed * 2.2 + p.phase) * (0.12 * p.jitter * p.breathOffset);

      let px = p.x * sx;
      let py = p.y * sy;

      if (this.pointer.inside && p.n > 0.48 && !this.reducedMotion) {
        const dx = this.pointer.x - px;
        const dy = this.pointer.y - py;
        const d = Math.max(1, Math.hypot(dx, dy));
        const influence = clamp(1 - d / (size * 0.43), 0, 1);
        const edgeWeight = Math.pow((p.n - 0.48) / 0.52, 1.1);
        const pull = influence * edgeWeight * size * 0.035;
        px += (dx / d) * pull;
        py += (dy / d) * pull;
      }

      let rippleScale = 1;
      for (const ripple of this.ripples) {
        const rp = clamp(ripple.age / ripple.duration, 0, 1);
        const waveRadius = easeOutCubic(rp) * size * 0.58;
        const d = Math.hypot(px - ripple.x, py - ripple.y);
        const band = Math.max(0, 1 - Math.abs(d - waveRadius) / (size * 0.075));
        rippleScale += band * (1 - rp) * 0.45;
      }

      const clickScale = 1 + this.clickPulse * (1 - p.n) * 0.03;
      const radius = p.baseRadius * localBreath * rippleScale * clickScale;
      const alpha = clamp(p.opacity * (0.94 + Math.sin(this.time + p.phase) * 0.035), 0.08, 1);

      ctx.globalAlpha = alpha;
      ctx.fillStyle = colors.particle;
      ctx.beginPath();
      ctx.arc(px, py, radius, 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.globalAlpha = 1;
    this.drawFace(ctx, size, colors);
    ctx.restore();
  }

  drawFace(ctx, size, colors) {
    const eyeTravel = size * 0.08;
    const ex = this.eye.x * eyeTravel;
    const ey = this.eye.y * eyeTravel;

    const eyeWidth = size * 0.055;
    const shortH = size * 0.20;
    const tallH = size * 0.31;

    const baseline = -size * 0.015;

    const radius = eyeWidth * 0.42;
    const gap = size * 0.118;

    const drawRoundedRect = (x, bottom, w, h, r, color) => {
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.roundRect(x, bottom - h, w, h, r);
      ctx.fill();
    };

    let blink = 1;
    if (!this.reducedMotion) {
      const blinkWave = (Math.sin(this.time * 1.8) + 1) / 2;
      if (blinkWave > 0.94) {
        blink = 0.15;
      }
    }

    drawRoundedRect(
      -gap - eyeWidth / 2 + ex,
      baseline + ey,
      eyeWidth,
      shortH * blink,
      radius,
      colors.face
    );

    drawRoundedRect(
      gap - eyeWidth / 2 + ex,
      baseline + ey,
      eyeWidth,
      tallH * blink,
      radius,
      colors.face
    );

    const mouthY = size * 0.11;

    if (!this.speaking) {
      const mouthW = size * 0.15;
      const mouthH = size * 0.035;
      drawRoundedRect(
        -mouthW / 2,
        mouthY + mouthH / 2,
        mouthW,
        mouthH,
        mouthH / 2,
        colors.face
      );
      return;
    }

    const wave = (Math.sin(this.mouthPhase) + 1) / 2;
    const mouthW = size * (0.11 + wave * 0.075);
    const mouthH = size * (0.08 + wave * 0.12);

    ctx.fillStyle = colors.mouthOpen;
    ctx.beginPath();
    ctx.ellipse(0, mouthY, mouthW / 2, mouthH / 2, 0, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = colors.teeth;
    ctx.beginPath();
    ctx.roundRect(
      -mouthW * 0.36,
      mouthY - mouthH * 0.45,
      mouthW * 0.72,
      mouthH * 0.22,
      mouthH * 0.1
    );
    ctx.fill();

    ctx.fillStyle = colors.tongue;
    ctx.beginPath();
    ctx.ellipse(
      0,
      mouthY + mouthH * 0.28,
      mouthW * 0.26,
      mouthH * 0.13,
      0,
      0,
      Math.PI * 2
    );
    ctx.fill();
  }

  frame(now) {
    const dt = clamp((now - this.lastFrame) / 1000, 0, 0.033);
    this.lastFrame = now;
    this.update(dt, now);
    this.draw();
    this._raf = requestAnimationFrame(this.frame);
  }
}

if (!customElements.get("rule-mirror-mascot")) {
  customElements.define("rule-mirror-mascot", RuleMirrorMascot);
}
