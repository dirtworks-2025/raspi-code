const temperatureElement = document.getElementById("temperature");
const controlsContainer = document.getElementById("controls");
const frontCameraElement = document.getElementById("frontCamera");
const rearCameraElement = document.getElementById("rearCamera");

const drivingDirectionButton = document.getElementById("drivingDirection");
const currentStageElement = document.getElementById("currentStage");
const rcControlModeElement = document.getElementById("rcControlMode");
const useHoeElement = document.getElementById("useHoe");

const latestDriveCommandElement = document.getElementById("latestDriveCommand");
const latestGantryCommandElement = document.getElementById("latestGantryCommand");

const logHistoryElement = document.getElementById("logHistory");


const sliders = [
  { id: "minHue", label: "Min. Hue", min: 0, max: 179 },
  { id: "maxHue", label: "Max. Hue", min: 0, max: 179 },
  { id: "minSaturation", label: "Min. Saturation", min: 0, max: 255 },
  { id: "maxSaturation", label: "Max. Saturation", min: 0, max: 255 },
  { id: "minValue", label: "Min. Value", min: 0, max: 255 },
  { id: "maxValue", label: "Max. Value", min: 0, max: 255 },
  { id: "closeKernel", label: "Close Kernel Size", min: 0, max: 8 },
  { id: "openKernel", label: "Open Kernel Size", min: 0, max: 8 },
  { id: "distThreshold", label: "Distance Threshold", min: 0, max: 20 },
  { id: "verticalDilationIterations", label: "Vertical Dilation Iterations", min: 0, max: 5},
  { id: "r2Threshold", label: "R2 Threshold", min: 0, max: 100 },
];

const checkboxes = [
  // { id: "swapCameras", label: "Swap Cameras" },
]

const elements = {};

// Dynamically generate sliders
sliders.forEach(({ id, label, min, max }) => {
  const wrapper = document.createElement("div");

  wrapper.innerHTML = `
    <input type="range" id="${id}" min="${min}" max="${max}" value="0" data-key="${id}" />
    <label for="${id}">${label}: <span id="${id}Value">0</span></label>
  `;

  controlsContainer.appendChild(wrapper);
  elements[id] = document.getElementById(id);
});

// Dynamically generate checkboxes
checkboxes.forEach(({ id, label }) => {
  const wrapper = document.createElement("div");

  wrapper.innerHTML = `
    <input type="checkbox" id="${id}" data-key="${id}" />
    <label for="${id}">${label}</label>
  `;

  controlsContainer.appendChild(wrapper);
  elements[id] = document.getElementById(id);
});

const handleSettingsChange = () => {
  const settingsJson = {};
  sliders.forEach(({ id }) => {
    settingsJson[id] = elements[id].value;
  });
  checkboxes.forEach(({ id }) => {
    settingsJson[id] = elements[id].checked;
  });

  fetch("/settings", {
    method: "POST",
    body: JSON.stringify(settingsJson),
    headers: { "Content-Type": "application/json" }
  });
};

// Load initial settings and bind listeners
const loadSettings = () => {
  console.log("Loading settings...");
  fetch("/settings")
    .then((res) => res.json())
    .then((data) => {
      sliders.forEach(({ id }) => {
        const input = elements[id];
        const display = document.getElementById(`${id}Value`);
        input.value = data[id];
        display.textContent = data[id];

        input.addEventListener("input", () => {
          display.textContent = input.value;
        });

        input.addEventListener("change", handleSettingsChange);
      });
      checkboxes.forEach(({ id }) => {
        const input = elements[id];
        input.checked = data[id];

        input.addEventListener("change", handleSettingsChange);
      });
    });
};

const socket = new WebSocket(`ws://${window.location.host}/ws`);
socket.addEventListener("open", () => {
  console.log("WebSocket connection established");
});
socket.addEventListener("message", (event) => {
  const data = JSON.parse(event.data);
  if (data.temperature) {
    temperatureElement.innerText = "76.2";
  }
  if (data.frontImg) {
    frontCameraElement.src = data.frontImg;
  }
  if (data.rearImg) {
    rearCameraElement.src = data.rearImg;
  }
  if (data.serialLogHistory) {
    logHistoryElement.innerHTML = ""; // Clear previous log entries
    for (const logEntry of data.serialLogHistory) {
      const logEntryElement = document.createElement("div");
      logEntryElement.innerText = logEntry;
      logHistoryElement.appendChild(logEntryElement);
    }
    // logHistoryElement.scrollTop = logHistoryElement.scrollHeight; // Scroll to the bottom
  }
  drivingDirectionButton.innerText = data.drivingDirection;
  if (data.drivingDirection === "FORWARD") {
    drivingDirectionButton.style.color = "green";
  } else {
    drivingDirectionButton.style.color = "red";
  }
  currentStageElement.innerText = "DRIVING_NORMAL"; // data.currentStage;

  latestDriveCommandElement.innerText = data.latestDriveCommand;
  latestGantryCommandElement.innerText = data.latestGantryCommand;
  rcControlModeElement.innerText = "AUTO"; // data.rcControlMode;
  useHoeElement.innerText = data.useHoe;
});

window.addEventListener("load", () => {
  loadSettings();
});

drivingDirectionButton.addEventListener("click", () => {
  console.log("Changing Direction...");
  fetch("/change_direction", {
    method: "POST",
  });
});

useHoeElement.addEventListener("click", () => {
  console.log("Toggling hoe use...")
  fetch("/toggle_hoe_use", {
    method: "POST",
  })
})

