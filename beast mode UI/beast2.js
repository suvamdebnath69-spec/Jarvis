/* =====================================================
   NOVA BEAST MODE ENGINE
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
   POWER
===================================================== */

const powerValue =
    document.getElementById("powerValue");

const powerBar =
    document.getElementById("powerBar");


function updatePower() {

    const power =
        Math.floor(
            Math.random() * 8
        ) + 84;

    powerValue.textContent =
        power;

    powerBar.style.width =
        power + "%";
}


setInterval(
    updatePower,
    3000
);


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
   COMMAND SYSTEM
===================================================== */

const commandInput =
    document.getElementById(
        "commandInput"
    );

const sendCommand =
    document.getElementById(
        "sendCommand"
    );


function executeCommand() {

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


    commandInput.value = "";


    /*
        DEMO PROCESSING

        Later replace this with
        your NOVA Python backend.
    */


    setTimeout(() => {

        addActivity(
            "COMMAND PROCESSING COMPLETE"
        );

        setIdle();

    }, 3500);

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
   DEMO TASK
===================================================== */

/*

   When NOVA actually starts
   doing something, call:

       setTask(
           "Analyzing files",
           "Searching NOVA project..."
       );


   Other examples:

       setTask(
           "Writing code",
           "Generating Python module..."
       );


       setTask(
           "Searching web",
           "Gathering information..."
       );


   When finished:

       setIdle();

*/


/* =====================================================
   INITIAL STATE
===================================================== */

setIdle();

addActivity(
    "NOVA BEAST MODE INITIALIZED"
);

addActivity(
    "NEURAL ENGINE ONLINE"
);

addActivity(
    "WAITING FOR COMMAND"
);