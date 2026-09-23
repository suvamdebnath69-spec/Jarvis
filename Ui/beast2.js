/* =====================================================
   NOVA BEAST MODE ENGINE — wired to the Python backend
   Design & visual states per beast1.css / Beast.html.
   The demo simulation is now real /api calls.
===================================================== */


/* =====================================================
   CLOCK
===================================================== */

const timeElement =
    document.getElementById("time");


function updateClock() {

    const now = new Date();

    const hours =
        String(now.getHours()).padStart(2, "0");

    const minutes =
        String(now.getMinutes()).padStart(2, "0");

    const seconds =
        String(now.getSeconds()).padStart(2, "0");

    timeElement.textContent =
        `${hours}:${minutes}:${seconds}`;
}


setInterval(updateClock, 1000);

updateClock();


/* =====================================================
   BACKEND HELPERS
===================================================== */

async function api(path, body) {

    const options = body
        ? {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(body),
          }
        : undefined;

    return (await fetch(path, options)).json();

}


/* =====================================================
   POWER (live system headroom from the backend)
===================================================== */

const powerValue =
    document.getElementById("powerValue");

const powerBar =
    document.getElementById("powerBar");


function updatePower(power) {

    powerValue.textContent =
        power;

    powerBar.style.width =
        power + "%";
}


/* =====================================================
   TASK SYSTEM
===================================================== */

const taskList =
    document.getElementById("taskList");

const taskCount =
    document.getElementById("taskCount");

const systemStatus =
    document.getElementById("systemStatus");

const systemDescription =
    document.getElementById(
        "systemDescription"
    );


function setTask(
    taskName,
    description = "Processing..."
) {

    taskList.innerHTML = `

        <div class="active-task">

            <div
                style="
                    display:flex;
                    align-items:center;
                    gap:10px;
                    padding:18px 0;
                "
            >

                <div
                    style="
                        width:9px;
                        height:9px;
                        border-radius:50%;
                        background:#ff1a1a;
                        box-shadow:0 0 12px #ff0000;
                    "
                ></div>

                <div>

                    <strong
                        style="
                            display:block;
                            color:#fff;
                            font-size:11px;
                        "
                    >
                        ${taskName}
                    </strong>

                    <small
                        style="
                            display:block;
                            margin-top:5px;
                            color:#666;
                            font-size:8px;
                        "
                    >
                        ${description}
                    </small>

                </div>

            </div>

            <div
                style="
                    height:2px;
                    background:#220000;
                    overflow:hidden;
                "
            >

                <div
                    class="task-progress"
                    style="
                        height:100%;
                        width:20%;
                        background:#ff1a1a;
                        box-shadow:0 0 10px #ff0000;
                    "
                ></div>

            </div>

        </div>

    `;


    taskCount.textContent = "1";

    systemStatus.textContent =
        "WORKING";

    systemDescription.textContent =
        taskName;
}


/* =====================================================
   IDLE
===================================================== */

function setIdle() {

    taskList.innerHTML = `

        <div class="idle-state">

            <div class="idle-icon">
                //
            </div>

            <strong>
                IDLE
            </strong>

            <small>
                No active operations
            </small>

        </div>

    `;


    taskCount.textContent = "0";


    systemStatus.textContent =
        "ACTIVE";

    systemDescription.textContent =
        "NOVA systems operational";
}


/* =====================================================
   ACTIVITY LOG
===================================================== */

const activityLog =
    document.getElementById(
        "activityLog"
    );


function addActivity(message) {

    const now = new Date();

    const timestamp =
        [
            now.getHours(),
            now.getMinutes(),
            now.getSeconds()
        ]
        .map(
            value =>
                String(value).padStart(2, "0")
        )
        .join(":");


    const entry =
        document.createElement("div");


    entry.innerHTML = `
        <span>${timestamp}</span>
        ${message}
    `;


    activityLog.prepend(entry);


    while (
        activityLog.children.length > 6
    ) {

        activityLog.removeChild(
            activityLog.lastChild
        );

    }
}


/* =====================================================
   COMMAND SYSTEM — real backend
===================================================== */

const commandInput =
    document.getElementById(
        "commandInput"
    );

const sendCommand =
    document.getElementById(
        "sendCommand"
    );

const commandStatus =
    document.querySelector(".command-status");


async function executeCommand() {

    const command =
        commandInput.value.trim();


    if (!command) {
        return;
    }


    addActivity(
        "COMMAND RECEIVED"
    );


    setTask(
        "Processing command",
        command
    );

    commandStatus.textContent = "BUSY";

    commandInput.value = "";


    try {

        const data = await api("/api/command", { text: command });

        addActivity("COMMAND COMPLETE");

        if (data.reply) {
            addActivity(data.reply.slice(0, 42).toUpperCase());
        }

        /* "come back to normal mode" IS the exit trigger */
        if (data.intent === "BEAST_OFF") {
            standby();
            return;
        }

    } catch (error) {

        addActivity("BACKEND UNREACHABLE");

    }

    commandStatus.textContent = "READY";

    setIdle();

}


sendCommand.addEventListener(
    "click",
    executeCommand
);


commandInput.addEventListener(
    "keydown",
    event => {

        if (
            event.key === "Enter"
        ) {

            executeCommand();

        }

    }
);


/* =====================================================
   LIVE STATE POLLING
===================================================== */

let lastAnnouncementId = 0;   // read announcements by cursor — none are missed

async function poll() {

    try {

        const s = await api("/api/state");

        updatePower(s.stats.overall);

        if (s.status === "idle") {
            setIdle();
        } else {
            setTask(
                s.status.toUpperCase(),
                s.detail || "Working..."
            );
        }

        const d = await api("/api/announcements?since=" + lastAnnouncementId);

        d.announcements.forEach(a =>
            addActivity("REMINDER: " + a.text.slice(0, 34).toUpperCase())
        );

        lastAnnouncementId = d.last_id;

    } catch (error) {

        addActivity("BACKEND OFFLINE");

    }

}


setInterval(poll, 2000);


/* =====================================================
   KILL SWITCH — ESC disarms instantly
   "come back to normal mode" triggers the same path
===================================================== */

document.addEventListener("keydown", event => {

    if (event.key === "Escape") {
        addActivity("KILL SWITCH — STANDING DOWN");
        standby();
    }

});

/* -----------------------------------------
   RETURN SOUND — descending sweep, normal mode
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

function playStandDownSound() {
    try {
        const ctx = audioCtx();
        const now = ctx.currentTime;

        /* descending sweep */
        const sweep = ctx.createOscillator();
        const sweepGain = ctx.createGain();
        sweep.type = "sawtooth";
        sweep.frequency.setValueAtTime(320, now);
        sweep.frequency.exponentialRampToValueAtTime(70, now + 0.55);
        sweepGain.gain.setValueAtTime(0.0001, now);
        sweepGain.gain.exponentialRampToValueAtTime(0.18, now + 0.15);
        sweepGain.gain.exponentialRampToValueAtTime(0.0001, now + 0.6);
        sweep.connect(sweepGain).connect(ctx.destination);
        sweep.start(now);
        sweep.stop(now + 0.65);

        /* soft resolution tone */
        const bell = ctx.createOscillator();
        const bellGain = ctx.createGain();
        bell.type = "sine";
        bell.frequency.setValueAtTime(520, now + 0.35);
        bellGain.gain.setValueAtTime(0.0001, now + 0.35);
        bellGain.gain.exponentialRampToValueAtTime(0.12, now + 0.4);
        bellGain.gain.exponentialRampToValueAtTime(0.0001, now + 0.9);
        bell.connect(bellGain).connect(ctx.destination);
        bell.start(now + 0.35);
        bell.stop(now + 0.95);
    } catch (error) {
        /* audio unavailable — the stand-down still proceeds */
    }
}


/* standby control in the footer (keeps Beast.html untouched) */

const footer =
    document.querySelector(".footer");

if (footer) {

    const back =
        document.createElement("div");

    back.innerHTML =
        '<a href="/" onclick="standby(); return false;" ' +
        'style="color:#ff1a1a;text-decoration:none;letter-spacing:2px;">' +
        '&#9211; STANDBY (ESC)</a>';

    footer.appendChild(back);

}


/* =====================================================
   DEMO NEURAL ACTIVITY
===================================================== */

const nodes =
    document.querySelectorAll(
        ".node"
    );


nodes.forEach(
    (node, index) => {

        node.style.animationDelay =
            `${index * 0.12}s`;

    }
);


/* =====================================================
   ENTRANCE / EXIT TRANSITIONS
===================================================== */

/* arrive: red boot flash + staggered panel drop-in */

document.body.classList.add("beast-enter");

const bootFlash = document.createElement("div");
bootFlash.className = "beast-boot";
document.body.appendChild(bootFlash);

bootFlash.addEventListener("animationend", () => bootFlash.remove());

setTimeout(
    () => document.body.classList.remove("beast-enter"),
    900
);


/* leave: red flash collapse -> / (also triggered by ESC kill switch) */

async function standby() {

    if (document.body.classList.contains("stand-down")) {
        return;
    }
    document.body.classList.add("stand-down");

    playStandDownSound();

    const outFlash = document.createElement("div");
    outFlash.className = "beast-boot";
    outFlash.style.animationDirection = "reverse";
    outFlash.style.animationDuration = "0.35s";
    document.body.appendChild(outFlash);

    try {
        await api("/api/beast", { enabled: false });
    } catch (error) {
        /* backend gone — still leave */
    }

    setTimeout(() => {
        location.href = "/";
    }, 380);

}


/* =====================================================
   ARM ON LOAD
===================================================== */

setIdle();

addActivity(
    "NOVA BEAST MODE INITIALIZED"
);

addActivity(
    "NEURAL ENGINE ONLINE"
);

api("/api/beast", { enabled: true })
    .then(() => addActivity("BEAST MODE ARMED"))
    .catch(() => addActivity("ARMING FAILED — BACKEND OFFLINE"));
