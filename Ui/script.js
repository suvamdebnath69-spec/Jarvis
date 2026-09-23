/* =========================================
   NOVA CORE — wired to the Python backend
   Visual states & design hooks unchanged;
   the demo simulation is now real /api calls.
========================================= */

const status = document.getElementById("status");
const statusDetail = document.getElementById("status-detail");
const statusLight = document.querySelector(".status-light");

const taskContent = document.getElementById("task-content");
const taskIndicator = document.querySelector(".task-indicator");

const input = document.getElementById("chat-input");
const sendButton = document.getElementById("send-button");

/* chat log — injected so conversation has somewhere to live,
   styled to match the design (see .chat-log in style.css) */
const chatLog = document.createElement("div");
chatLog.className = "chat-log";
document.body.appendChild(chatLog);

function addMsg(role, text) {

    const div = document.createElement("div");
    div.className = "chat-msg " + role;

    const who = document.createElement("span");
    who.className = "who";
    who.textContent = role === "user" ? "YOU" : "NOVA";

    const body = document.createElement("div");
    body.textContent = text;

    div.append(who, body);
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;

}


/* =========================================
   NOVA STATUS
========================================= */

const STATUS_LABELS = {
    idle: ["ACTIVE", "NOVA is ready"],
    listening: ["LISTENING", "Microphone open"],
    thinking: ["THINKING", "Processing..."],
    speaking: ["SPEAKING", "Talking"],
};

function setStatus(state, detail) {

    status.textContent = state;
    statusDetail.textContent = detail;
    statusLight.classList.toggle("busy", state !== "ACTIVE");

}


/* =========================================
   TASK SYSTEM
========================================= */

function setTask(taskName, detail = "Working...") {

    taskContent.innerHTML = `
        <div class="idle">

            <div
                class="idle-dot"
                style="
                    background:#d9a928;
                    box-shadow:0 0 10px #d9a928;
                "
            ></div>

            <div>

                <strong style="color:#ffd85c">
                    ${taskName}
                </strong>

                <small>
                    ${detail}
                </small>

            </div>

        </div>
    `;

    taskIndicator.style.background = "#d9a928";

    taskIndicator.style.boxShadow =
        "0 0 10px rgba(217,169,40,.7)";

    setStatus(taskName.toUpperCase(), detail);
}


function setIdle() {

    taskContent.innerHTML = `
        <div class="idle">

            <div class="idle-dot"></div>

            <div>

                <strong>IDLE</strong>

                <small>
                    No active tasks
                </small>

            </div>

        </div>
    `;

    taskIndicator.style.background = "#555";

    taskIndicator.style.boxShadow = "none";

    setStatus(
        "ACTIVE",
        "NOVA is ready"
    );

}


/* =========================================
   CHAT — real backend
========================================= */

async function sendMessage() {

    const message = input.value.trim();

    if (!message) {
        return;
    }

    addMsg("user", message);
    setTask("Processing", message);
    input.value = "";

    try {

        const response = await fetch("/api/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ text: message }),
        });

        const data = await response.json();
        addMsg("nova", data.reply || "...");

        /* globe reacts to NOVA's actual classification */
        if (window.NovaGlobe) {
            NovaGlobe.setPhrase(message);
            NovaGlobe.pulse();
        }

        /* the command "enter beast mode" IS the transition trigger */
        if (data.intent === "BEAST_ON") {
            enterBeastMode();
            return;
        }

    } catch (error) {
        addMsg("nova", "The backend is unreachable, sir.");
    }

    setIdle();

}


sendButton.addEventListener(
    "click",
    sendMessage
);


input.addEventListener(
    "keydown",
    (event) => {

        if (event.key === "Enter") {
            sendMessage();
        }

    }
);


/* =========================================
   LIVE STATE POLLING
========================================= */

let lastAnnouncementId = 0;   // read announcements by cursor — none are missed

async function poll() {

    if (document.body.classList.contains("to-beast")) {
        return;   // transition in progress — don't fight the status text
    }

    try {

        const s = await (
            await fetch("/api/state")
        ).json();

        const [label, sub] =
            STATUS_LABELS[s.status] || STATUS_LABELS.idle;

        if (s.status === "idle") {
            setIdle();
        } else {
            setTask(label, s.detail || "Working...");
        }

        const d = await (
            await fetch("/api/announcements?since=" + lastAnnouncementId)
        ).json();

        d.announcements.forEach(
            (a) => addMsg("nova", a.text)
        );

        lastAnnouncementId = d.last_id;

    } catch (error) {
        /* backend offline — stay calm */
    }

}


setInterval(poll, 2000);

poll();

/* =========================================
   BEAST MODE TRANSITION
   Gold UI powers down -> red shockwave -> /beast
   Triggered by COMMAND ONLY: "enter beast mode"
   (the header button was removed)
========================================= */

/* -----------------------------------------
   TRANSITION SOUNDS — WebAudio, no files
----------------------------------------- */

let _audioCtx = null;

function audioCtx() {
    if (!_audioCtx) {
        _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (_audioCtx.state === "suspended") {
        _audioCtx.resume();
    }
    return _audioCtx;
}

/* rising power-up sweep + impact: entering Beast Mode */
function playBeastSound() {
    try {
        const ctx = audioCtx();
        const now = ctx.currentTime;

        /* low rising sweep */
        const sweep = ctx.createOscillator();
        const sweepGain = ctx.createGain();
        sweep.type = "sawtooth";
        sweep.frequency.setValueAtTime(80, now);
        sweep.frequency.exponentialRampToValueAtTime(320, now + 0.85);
        sweepGain.gain.setValueAtTime(0.0001, now);
        sweepGain.gain.exponentialRampToValueAtTime(0.22, now + 0.5);
        sweepGain.gain.exponentialRampToValueAtTime(0.0001, now + 1.0);
        sweep.connect(sweepGain).connect(ctx.destination);
        sweep.start(now);
        sweep.stop(now + 1.05);

        /* impact thud at landing */
        const thud = ctx.createOscillator();
        const thudGain = ctx.createGain();
        thud.type = "sine";
        thud.frequency.setValueAtTime(150, now + 0.85);
        thud.frequency.exponentialRampToValueAtTime(40, now + 1.15);
        thudGain.gain.setValueAtTime(0.0001, now + 0.85);
        thudGain.gain.exponentialRampToValueAtTime(0.5, now + 0.88);
        thudGain.gain.exponentialRampToValueAtTime(0.0001, now + 1.25);
        thud.connect(thudGain).connect(ctx.destination);
        thud.start(now + 0.85);
        thud.stop(now + 1.3);

        /* white-noise hiss layer for texture */
        const len = ctx.sampleRate * 0.9;
        const buf = ctx.createBuffer(1, len, ctx.sampleRate);
        const data = buf.getChannelData(0);
        for (let i = 0; i < len; i++) {
            data[i] = (Math.random() * 2 - 1) * (1 - i / len);
        }
        const noise = ctx.createBufferSource();
        noise.buffer = buf;
        const noiseGain = ctx.createGain();
        noiseGain.gain.setValueAtTime(0.06, now);
        noiseGain.gain.exponentialRampToValueAtTime(0.0001, now + 0.9);
        noise.connect(noiseGain).connect(ctx.destination);
        noise.start(now);
    } catch (error) {
        /* audio blocked/unavailable — transition stays silent */
    }
}

function enterBeastMode() {

    if (document.body.classList.contains("to-beast")) {
        return;
    }
    document.body.classList.add("to-beast");

    playBeastSound();

    const overlay = document.createElement("div");
    overlay.className = "beast-transition";
    overlay.innerHTML = `
        <div class="red-veil"></div>
        <div class="shockwave"></div>
        <div class="shockwave w2"></div>
        <div class="shockwave w3"></div>
        <div class="launch-text">BEAST MODE</div>
    `;
    document.body.appendChild(overlay);

    /* force a reflow so the animations always start clean */
    void overlay.offsetWidth;
    overlay.classList.add("active");

    setStatus("BEAST MODE", "Arming expanded systems...");

    setTimeout(() => {
        location.href = "/beast";
    }, 950);

}

/* Start idle */

setIdle();


/* ================= LIVE NEURAL GLOBE ================= */

/* Renders NOVA's real classifier in 3D. Typing in the chatbox
   previews the activation path instantly; the globe also pulses
   when NOVA replies. Drag to rotate, wheel to zoom. */

(function () {

    const el = document.getElementById("globe-canvas");
    if (!el || !window.NovaGlobe) {
        return;
    }

    const ok = NovaGlobe.init(el, "gold");

    if (!ok) {
        return;
    }

    input.addEventListener("input", () => {
        NovaGlobe.setPhrase(input.value);
    });

})();
