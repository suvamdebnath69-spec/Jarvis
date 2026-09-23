/* =====================================================
   NOVA 3D NEURAL GLOBE — dependency-free WebGL

   Renders NOVA's ACTUAL trained classifier as a rotating
   3D network: vocab words (outer shell) -> 64 hidden
   neurons (middle) -> 43 intents (inner core). Weight
   lines come from Ui/globe_weights.json; sending a phrase
   through setPhrase() lights up the real activation path
   and fires pulse particles along the strongest edges.

   Theme: the canvas element carries data-theme="gold" or
   "red" — the globe recolors itself accordingly.

   Usage:
     NovaGlobe.init(document.getElementById('globe-canvas'));
     NovaGlobe.setPhrase('open chrome');
     NovaGlobe.pulse();          // burst when NOVA replies
===================================================== */

var NovaGlobe = (function () {
    "use strict";

    /* ---------------- state ---------------- */

    let canvas = null;
    let gl = null;
    let ready = false;
    let theme = "gold";

    const THEMES = {
        gold: {
            word:  [0.36, 0.29, 0.12],
            wordOn: [1.0, 0.84, 0.45],
            hidden: [0.30, 0.24, 0.10],
            intent: [0.94, 0.60, 0.48],
            winner: [1.0, 0.82, 0.48],
            line:   [1.0, 0.85, 0.55],
            pulseA: [1.0, 0.95, 0.80],
            pulseB: [1.0, 0.78, 0.45],
            clear:  [0.0, 0.0, 0.0]
        },
        red: {
            word:  [0.42, 0.05, 0.05],
            wordOn: [1.0, 0.35, 0.28],
            hidden: [0.35, 0.04, 0.04],
            intent: [0.95, 0.25, 0.20],
            winner: [1.0, 0.42, 0.32],
            line:   [1.0, 0.30, 0.25],
            pulseA: [1.0, 0.60, 0.50],
            pulseB: [1.0, 0.25, 0.20],
            clear:  [0.0, 0.0, 0.0]
        }
    };
    let pal = THEMES.gold;

    /* ---------------- model ---------------- */

    let words = [];
    let intents = [];
    let b1 = [];
    let edges1 = [];
    let edges2 = [];
    const hiddenAct = [];   // cached per-phrase activations
    const probs = [];       // cached per-phrase probabilities

    function tokenize(s) {
        return (s.toLowerCase().replace(/\u2019/g, "'").match(/[a-z']+/g) || []);
    }

    function classify(text) {
        const active = new Set();
        for (const w of tokenize(text)) {
            const i = wordIndex[w];
            if (i !== undefined) active.add(i);
        }
        const hidden = b1.map(function (b) {
            let s = b;
            active.forEach(function (i) { s += edgesIn[i] ? edgesIn[i].sum : 0; });
            return Math.max(0, s);
        });
        const outRaw = intents.map(function (_, k) {
            let s = 0;
            for (const e of edges2ByTarget[k]) s += hidden[e.j] * e.w;
            return s;
        });
        let maxR = -Infinity;
        for (const v of outRaw) if (v > maxR) maxR = v;
        let sum = 0;
        const exps = outRaw.map(function (v) { const e = Math.exp(v - maxR); sum += e; return e; });
        const p = exps.map(function (e) { return e / sum; });

        hiddenAct.length = 0; hiddenAct.push.apply(hiddenAct, hidden);
        probs.length = 0; probs.push.apply(probs, p);
        return { active: active, hidden: hidden, probs: p };
    }

    /* Approximation note: edges1 holds only the top-900 |w| edges of W1.
       For the hidden pre-activation we add the sum of exported weights per
       (input,hidden) pair and scale by (774*64)/900 so the activation
       profile matches the real network closely enough to light the same
       paths; the backend classifier remains the source of truth. */
    const edgesIn = {};  // inputIdx -> {sum, list}
    const edges2ByTarget = []; // intentIdx -> [{j,w}]

    /* ---------------- shaders ---------------- */

    const VS = [
        "attribute vec3 aPos;",
        "attribute vec3 aColor;",
        "uniform mat4 uMVP;",
        "uniform float uPointSize;",
        "varying vec3 vColor;",
        "void main(){",
        "  vColor = aColor;",
        "  gl_Position = uMVP * vec4(aPos, 1.0);",
        "  gl_PointSize = uPointSize;",
        "}"
    ].join("\n");

    const FS = [
        "precision mediump float;",
        "varying vec3 vColor;",
        "void main(){ gl_FragColor = vec4(vColor, 1.0); }"
    ].join("\n");

    /* ---------------- matrix helpers ---------------- */

    function perspective(out, fovy, aspect, near, far) {
        const f = 1.0 / Math.tan(fovy / 2);
        out[0] = f / aspect; out[1] = 0; out[2] = 0; out[3] = 0;
        out[4] = 0; out[5] = f; out[6] = 0; out[7] = 0;
        out[8] = 0; out[9] = 0; out[10] = (far + near) / (near - far);
        out[11] = -1;
        out[12] = 0; out[13] = 0; out[14] = (2 * far * near) / (near - far); out[15] = 0;
        return out;
    }

    function multiply(out, a, b) {
        for (let c = 0; c < 4; c++) {
            for (let r = 0; r < 4; r++) {
                out[c * 4 + r] =
                    a[r] * b[c * 4] +
                    a[4 + r] * b[c * 4 + 1] +
                    a[8 + r] * b[c * 4 + 2] +
                    a[12 + r] * b[c * 4 + 3];
            }
        }
        return out;
    }

    const proj = new Float32Array(16);
    const view = new Float32Array(16);
    const model = new Float32Array(16);
    const mvp = new Float32Array(16);
    const tmp = new Float32Array(16);

    function rotationY(out, a) {
        const c = Math.cos(a), s = Math.sin(a);
        out[0] = c; out[1] = 0; out[2] = -s; out[3] = 0;
        out[4] = 0; out[5] = 1; out[6] = 0; out[7] = 0;
        out[8] = s; out[9] = 0; out[10] = c; out[11] = 0;
        out[12] = 0; out[13] = 0; out[14] = 0; out[15] = 1;
        return out;
    }

    function rotationX(out, a) {
        const c = Math.cos(a), s = Math.sin(a);
        out[0] = 1; out[1] = 0; out[2] = 0; out[3] = 0;
        out[4] = 0; out[5] = c; out[6] = s; out[7] = 0;
        out[8] = 0; out[9] = -s; out[10] = c; out[11] = 0;
        out[12] = 0; out[13] = 0; out[14] = 0; out[15] = 1;
        return out;
    }

    function translationZ(out, z) {
        out[0] = 1; out[1] = 0; out[2] = 0; out[3] = 0;
        out[4] = 0; out[5] = 1; out[6] = 0; out[7] = 0;
        out[8] = 0; out[9] = 0; out[10] = 1; out[11] = 0;
        out[12] = 0; out[13] = 0; out[14] = z; out[15] = 1;
        return out;
    }

    /* ---------------- geometry ---------------- */

    function fibonacciSphere(n, radius) {
        const pts = new Float32Array(n * 3);
        const golden = Math.PI * (3 - Math.sqrt(5));
        for (let i = 0; i < n; i++) {
            const y = 1 - (i / (n - 1 || 1)) * 2;
            const r = Math.sqrt(1 - y * y);
            const theta = golden * i;
            pts[i * 3] = Math.cos(theta) * r * radius;
            pts[i * 3 + 1] = y * radius;
            pts[i * 3 + 2] = Math.sin(theta) * r * radius;
        }
        return pts;
    }

    const LINES_PER_E1 = 900, LINES_PER_E2 = 150;

    let wordPts, hiddenPts, intentPts;
    let wordCount, hiddenCount, intentCount;

    // GL buffers
    let prog, uMVP, uPointSize;
    let wordBuf, hiddenBuf, intentBuf;      // positions
    let wordColBuf, hiddenColBuf, intentColBuf; // colors
    let lineBuf1, lineColBuf1, lineCount1;
    let lineBuf2, lineColBuf2, lineCount2;
    let pulseBuf, pulseColBuf;

    const MAX_PULSES = 90;
    const pulsePos = new Float32Array(MAX_PULSES * 3);
    const pulseCol = new Float32Array(MAX_PULSES * 3);
    let pulseEdges = [];
    let burstT = 0;

    /* ---------------- colors ---------------- */

    function setColors(buf, count, base, mul) {
        const c = new Float32Array(count * 3);
        for (let i = 0; i < count; i++) {
            c[i * 3] = base[0] * mul;
            c[i * 3 + 1] = base[1] * mul;
            c[i * 3 + 2] = base[2] * mul;
        }
        gl.bindBuffer(gl.ARRAY_BUFFER, buf);
        gl.bufferData(gl.ARRAY_BUFFER, c, gl.DYNAMIC_DRAW);
        return c;
    }

    /* ---------------- pulses ---------------- */

    function rebuildPulseEdges(res) {
        const activeArr = Array.from(res.active);
        const wordEdges = [];
        for (const i of activeArr) {
            const list = edgesIn[i] ? edgesIn[i].list : [];
            for (const e of list) wordEdges.push({ i: i, j: e.j, w: Math.abs(e.w) });
        }
        wordEdges.sort(function (a, b) { return b.w - a.w; });

        const maxP = Math.max.apply(null, res.probs);
        const winner = res.probs.indexOf(maxP);
        const hidEdges = [];
        for (let j = 0; j < hiddenCount; j++) {
            if (res.hidden[j] <= 0) continue;
            hidEdges.push({ j: j, k: winner, w: Math.abs(w2get(j, winner)) * res.hidden[j] });
        }
        hidEdges.sort(function (a, b) { return b.w - a.w; });

        pulseEdges = [];
        wordEdges.slice(0, 55).forEach(function (e) {
            pulseEdges.push({ from: e.i, to: e.j, layer: 0, color: pal.pulseA, offset: Math.random() });
        });
        hidEdges.slice(0, 30).forEach(function (e) {
            pulseEdges.push({ from: e.j, to: e.k, layer: 1, color: pal.pulseB, offset: Math.random() });
        });
        pulseEdges = pulseEdges.slice(0, MAX_PULSES);
    }

    let edges2Lookup = null;
    function w2get(j, k) {
        const e = edges2Lookup[j * intentCount + k];
        return e === undefined ? 0 : e;
    }

    /* ---------------- init ---------------- */

    function init(el) {
        canvas = el;
        gl = canvas.getContext("webgl", { alpha: true, antialias: true });
        if (!gl) {
            canvas.style.display = "none";
            return false;
        }

        fetch("globe_weights.json")
            .then(function (r) { return r.json(); })
            .then(function (data) {
                words = data.words;
                intents = data.intents;
                b1 = data.b1;
                edges1 = data.edges1;
                edges2 = data.edges2;
                wordIndex = {};
                words.forEach(function (w, i) { wordIndex[w] = i; });

                wordCount = words.length;
                hiddenCount = b1.length;
                intentCount = intents.length;

                for (const e of edges1) {
                    if (!edgesIn[e.i]) edgesIn[e.i] = { sum: 0, list: [] };
                    edgesIn[e.i].sum += e.w;
                    edgesIn[e.i].list.push(e);
                }
                const scale = (wordCount * hiddenCount) / edges1.length;
                for (const k of Object.keys(edgesIn)) edgesIn[k].sum *= scale;

                for (let k = 0; k < intentCount; k++) edges2ByTarget[k] = [];
                for (const e of edges2) edges2ByTarget[e.j].push(e);
                edges2Lookup = {};
                for (const e of edges2) edges2Lookup[e.j * intentCount + e.k] = e.w;

                buildScene();
                ready = true;
                classifyAndShow("");
            })
            .catch(function () {
                canvas.style.display = "none";
            });
        return true;
    }

    let wordIndex = {};

    function buildScene() {
        // compile program
        function shader(type, src) {
            const s = gl.createShader(type);
            gl.shaderSource(s, src);
            gl.compileShader(s);
            return s;
        }
        prog = gl.createProgram();
        gl.attachShader(prog, shader(gl.VERTEX_SHADER, VS));
        gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, FS));
        gl.linkProgram(prog);
        gl.useProgram(prog);
        uMVP = gl.getUniformLocation(prog, "uMVP");
        uPointSize = gl.getUniformLocation(prog, "uPointSize");
        const aPos = gl.getAttribLocation(prog, "aPos");
        const aColor = gl.getAttribLocation(prog, "aColor");

        wordPts = fibonacciSphere(wordCount, 380);
        hiddenPts = fibonacciSphere(hiddenCount, 190);
        intentPts = fibonacciSphere(intentCount, 70);

        wordBuf = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, wordBuf);
        gl.bufferData(gl.ARRAY_BUFFER, wordPts, gl.STATIC_DRAW);
        hiddenBuf = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, hiddenBuf);
        gl.bufferData(gl.ARRAY_BUFFER, hiddenPts, gl.STATIC_DRAW);
        intentBuf = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, intentBuf);
        gl.bufferData(gl.ARRAY_BUFFER, intentPts, gl.STATIC_DRAW);

        wordColBuf = gl.createBuffer();
        hiddenColBuf = gl.createBuffer();
        intentColBuf = gl.createBuffer();

        function lineGeom(edges, ptsFrom, ptsTo) {
            const pos = new Float32Array(edges.length * 6);
            edges.forEach(function (e, n) {
                const a = ptsFrom[e.i], b = ptsTo[e.j];
                pos.set([a[0], a[1], a[2], b[0], b[1], b[2]], n * 6);
            });
            return pos;
        }
        lineBuf1 = gl.createBuffer();
        const lp1 = lineGeom(edges1, wordPts, hiddenPts);
        lineCount1 = edges1.length * 2;
        gl.bindBuffer(gl.ARRAY_BUFFER, lineBuf1);
        gl.bufferData(gl.ARRAY_BUFFER, lp1, gl.STATIC_DRAW);
        lineBuf2 = gl.createBuffer();
        const lp2 = lineGeom(edges2, hiddenPts, intentPts);
        lineCount2 = edges2.length * 2;
        gl.bindBuffer(gl.ARRAY_BUFFER, lineBuf2);
        gl.bufferData(gl.ARRAY_BUFFER, lp2, gl.STATIC_DRAW);
        lineColBuf1 = gl.createBuffer();
        lineColBuf2 = gl.createBuffer();
        paintLines();

        pulseBuf = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, pulseBuf);
        gl.bufferData(gl.ARRAY_BUFFER, pulsePos, gl.DYNAMIC_DRAW);
        pulseColBuf = gl.createBuffer();
        gl.bindBuffer(gl.ARRAY_BUFFER, pulseColBuf);
        gl.bufferData(gl.ARRAY_BUFFER, pulseCol, gl.DYNAMIC_DRAW);

        canvas._aPos = aPos;
        canvas._aColor = aColor;

        gl.enable(gl.BLEND);
        gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
        gl.lineWidth(1.0);

        resize();
    }

    let lineColCache1 = null, lineColCache2 = null;
    function paintLines() {
        const max1 = edges1.length ? Math.abs(edges1[0].w) : 1;
        const c1 = new Float32Array(edges1.length * 6);
        edges1.forEach(function (e, n) {
            const a = 0.05 + (Math.abs(e.w) / max1) * 0.22;
            const r = pal.line[0] * a, g = pal.line[1] * a, b = pal.line[2] * a;
            c1.set([r, g, b, r, g, b], n * 6);
        });
        lineColCache1 = c1;
        gl.bindBuffer(gl.ARRAY_BUFFER, lineColBuf1);
        gl.bufferData(gl.ARRAY_BUFFER, c1, gl.DYNAMIC_DRAW);

        const max2 = edges2.length ? Math.abs(edges2[0].w) : 1;
        const c2 = new Float32Array(edges2.length * 6);
        edges2.forEach(function (e, n) {
            const a = 0.08 + (Math.abs(e.w) / max2) * 0.35;
            const r = pal.line[0] * a, g = pal.line[1] * a, b = pal.line[2] * a;
            c2.set([r, g, b, r, g, b], n * 6);
        });
        lineColCache2 = c2;
        gl.bindBuffer(gl.ARRAY_BUFFER, lineColBuf2);
        gl.bufferData(gl.ARRAY_BUFFER, c2, gl.DYNAMIC_DRAW);
    }

    /* ---------------- live updates ---------------- */

    function classifyAndShow(text) {
        if (!ready) return;
        const res = classify(text);
        rebuildPulseEdges(res);

        // words: dim unless active
        const cw = new Float32Array(wordCount * 3);
        for (let i = 0; i < wordCount; i++) {
            const m = res.active.has(i) ? 1.0 : 0.28;
            const base = res.active.has(i) ? pal.wordOn : pal.word;
            cw[i * 3] = base[0] * m; cw[i * 3 + 1] = base[1] * m; cw[i * 3 + 2] = base[2] * m;
        }
        gl.bindBuffer(gl.ARRAY_BUFFER, wordColBuf);
        gl.bufferData(gl.ARRAY_BUFFER, cw, gl.DYNAMIC_DRAW);

        // hidden: brightness by activation
        let maxH = 1;
        for (const h of res.hidden) if (h > maxH) maxH = h;
        const ch = new Float32Array(hiddenCount * 3);
        for (let j = 0; j < hiddenCount; j++) {
            const t = Math.min(1, res.hidden[j] / maxH);
            const m = 0.28 + t * 0.9;
            ch[j * 3] = pal.hidden[0] * m; ch[j * 3 + 1] = pal.hidden[1] * m; ch[j * 3 + 2] = pal.hidden[2] * m;
        }
        gl.bindBuffer(gl.ARRAY_BUFFER, hiddenColBuf);
        gl.bufferData(gl.ARRAY_BUFFER, ch, gl.DYNAMIC_DRAW);

        // intents: winner glows
        const maxP = Math.max.apply(null, res.probs);
        const ci = new Float32Array(intentCount * 3);
        for (let k = 0; k < intentCount; k++) {
            const isW = res.probs[k] === maxP;
            const base = isW ? pal.winner : pal.intent;
            const m = 0.3 + res.probs[k] * 1.2;
            ci[k * 3] = base[0] * m; ci[k * 3 + 1] = base[1] * m; ci[k * 3 + 2] = base[2] * m;
        }
        gl.bindBuffer(gl.ARRAY_BUFFER, intentColBuf);
        gl.bufferData(gl.ARRAY_BUFFER, ci, gl.DYNAMIC_DRAW);
    }

    /* ---------------- render loop ---------------- */

    function resize() {
        if (!gl) return;
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const w = canvas.clientWidth || 520;
        const h = canvas.clientHeight || 520;
        canvas.width = w * dpr;
        canvas.height = h * dpr;
        gl.viewport(0, 0, canvas.width, canvas.height);
    }
    window.addEventListener("resize", resize);

    let rotY = 0, rotX = -0.15, dragging = false, prevX = 0, prevY = 0, autoSpin = true;
    let camZ = 980;

    function bindDrag() {
        canvas.addEventListener("pointerdown", function (e) {
            dragging = true; autoSpin = false; prevX = e.clientX; prevY = e.clientY;
        });
        window.addEventListener("pointerup", function () { dragging = false; });
        window.addEventListener("pointermove", function (e) {
            if (dragging) {
                rotY += (e.clientX - prevX) * 0.005;
                rotX += (e.clientY - prevY) * 0.005;
                prevX = e.clientX; prevY = e.clientY;
            }
        });
        canvas.addEventListener("wheel", function (e) {
            camZ = Math.min(2200, Math.max(500, camZ + e.deltaY * 0.6));
        }, { passive: true });
    }

    const t0 = performance.now();
    function frame(now) {
        requestAnimationFrame(frame);
        if (!ready) return;
        const t = (now - t0) / 1000;
        if (autoSpin) rotY += 0.0016;

        perspective(proj, 0.9, canvas.width / Math.max(1, canvas.height), 1, 4000);
        translationZ(view, -camZ);
        rotationY(tmp, rotY);
        multiply(model, tmp, rotationX(mvp, rotX)); // reuse mvp as scratch
        multiply(tmp, view, model);
        multiply(mvp, proj, tmp);

        gl.clearColor(pal.clear[0], pal.clear[1], pal.clear[2], 0);
        gl.clear(gl.COLOR_BUFFER_BIT);
        gl.uniformMatrix4fv(uMVP, false, mvp);

        const aPos = canvas._aPos, aColor = canvas._aColor;
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        function draw(buf, colBuf, count, mode, ptSize) {
            gl.uniform1f(uPointSize, (ptSize || 1) * dpr);
            gl.bindBuffer(gl.ARRAY_BUFFER, buf);
            gl.vertexAttribPointer(aPos, 3, gl.FLOAT, false, 0, 0);
            gl.enableVertexAttribArray(aPos);
            gl.bindBuffer(gl.ARRAY_BUFFER, colBuf);
            gl.vertexAttribPointer(aColor, 3, gl.FLOAT, false, 0, 0);
            gl.enableVertexAttribArray(aColor);
            gl.drawArrays(mode, 0, count);
        }

        gl.uniform1f(uPointSize, 1.0);
        draw(lineBuf1, lineColBuf1, lineCount1, gl.LINES);
        draw(lineBuf2, lineColBuf2, lineCount2, gl.LINES);

        // pulses travel along the active path
        const fracBase = t * 0.5;
        for (let p = 0; p < MAX_PULSES; p++) {
            if (p < pulseEdges.length) {
                const e = pulseEdges[p];
                const from = e.layer === 0 ? wordPts : hiddenPts;
                const to = e.layer === 0 ? hiddenPts : intentPts;
                const f = ((fracBase + e.offset) % 1);
                const x = from[e.from * 3] + (to[e.to * 3] - from[e.from * 3]) * f;
                const y = from[e.from * 3 + 1] + (to[e.to * 3 + 1] - from[e.from * 3 + 1]) * f;
                const z = from[e.from * 3 + 2] + (to[e.to * 3 + 2] - from[e.from * 3 + 2]) * f;
                const fade = Math.sin(f * Math.PI);
                pulsePos[p * 3] = x; pulsePos[p * 3 + 1] = y; pulsePos[p * 3 + 2] = z;
                pulseCol[p * 3] = e.color[0] * fade;
                pulseCol[p * 3 + 1] = e.color[1] * fade;
                pulseCol[p * 3 + 2] = e.color[2] * fade;
            } else {
                pulsePos[p * 3] = 0; pulsePos[p * 3 + 1] = 0; pulsePos[p * 3 + 2] = -99999;
                pulseCol[p * 3] = 0; pulseCol[p * 3 + 1] = 0; pulseCol[p * 3 + 2] = 0;
            }
        }
        gl.bindBuffer(gl.ARRAY_BUFFER, pulseBuf);
        gl.bufferData(gl.ARRAY_BUFFER, pulsePos, gl.DYNAMIC_DRAW);
        gl.vertexAttribPointer(aPos, 3, gl.FLOAT, false, 0, 0);
        gl.enableVertexAttribArray(aPos);
        gl.bindBuffer(gl.ARRAY_BUFFER, pulseColBuf);
        gl.bufferData(gl.ARRAY_BUFFER, pulseCol, gl.DYNAMIC_DRAW);
        gl.vertexAttribPointer(aColor, 3, gl.FLOAT, false, 0, 0);
        gl.enableVertexAttribArray(aColor);
        gl.uniform1f(uPointSize, 5 * dpr);
        gl.drawArrays(gl.POINTS, 0, MAX_PULSES);

        // burst: brief shockwave when a reply lands
        if (burstT > 0) {
            burstT -= 0.02;
            const s = 1 + (1 - burstT) * 0.35;
            const save = mvp.slice();
            for (let i = 0; i < 16; i++) tmp[i] = save[i] * s;
            gl.uniformMatrix4fv(uMVP, false, tmp);
            draw(lineBuf1, lineColBuf1, lineCount1, gl.LINES);
            gl.uniformMatrix4fv(uMVP, false, mvp);
        }

        draw(wordBuf, wordColBuf, wordCount, gl.POINTS, 2.6);
        draw(hiddenBuf, hiddenColBuf, hiddenCount, gl.POINTS, 5.5);
        draw(intentBuf, intentColBuf, intentCount, gl.POINTS, 9);
    }
    requestAnimationFrame(frame);

    /* ---------------- public API ---------------- */

    let lastPhrase = "";
    return {
        init: function (el, themeName) {
            theme = themeName || el.getAttribute("data-theme") || "gold";
            pal = THEMES[theme] || THEMES.gold;
            const ok = init(el);
            if (ok) bindDrag();
            return ok;
        },
        setPhrase: function (text) {
            if (text !== lastPhrase) {
                lastPhrase = text;
                classifyAndShow(text);
            }
        },
        pulse: function () { burstT = 1; },
        setTheme: function (name) {
            pal = THEMES[name] || THEMES.gold;
            paintLines();
            classifyAndShow(lastPhrase);
        }
    };
})();
