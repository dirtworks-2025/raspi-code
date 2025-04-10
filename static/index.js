const temperatureElement = document.getElementById("temperature");
const controlsContainer = document.getElementById("controls");
const frontCameraElement = document.getElementById("frontCamera");
const rearCameraElement = document.getElementById("rearCamera");

const drivingDirectionButton = document.getElementById("drivingDirection");
const currentStageElement = document.getElementById("currentStage");
const rcControlModeElement = document.getElementById("rcControlMode");

const latestDriveCommandElement = document.getElementById("latestDriveCommand");
const latestGantryCommandElement = document.getElementById("latestGantryCommand");

const logHistoryElement = document.getElementById("logHistory");


const sliders = [
  { id: "hLowerPercentile", label: "Hue - Lower Percentile", min: 0, max: 100 },
  { id: "hUpperPercentile", label: "Hue - Upper Percentile", min: 0, max: 100 },
  { id: "sLowerPercentile", label: "Saturation - Lower Percentile", min: 0, max: 100 },
  { id: "sUpperPercentile", label: "Saturation - Upper Percentile", min: 0, max: 100 },
  { id: "vLowerPercentile", label: "Value - Lower Percentile", min: 0, max: 100 },
  { id: "vUpperPercentile", label: "Value - Upper Percentile", min: 0, max: 100 },
  { id: "closeKernel", label: "Close Kernel Size", min: 0, max: 8 },
  { id: "openKernel", label: "Open Kernel Size", min: 0, max: 8 },
  { id: "distThreshold", label: "Distance Threshold", min: 0, max: 20 },
];

const checkboxes = [
  { id: "swapCameras", label: "Swap Cameras" },
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
    temperatureElement.innerText = data.temperature;
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
    logHistoryElement.scrollTop = logHistoryElement.scrollHeight; // Scroll to the bottom
  }
  drivingDirectionButton.innerText = data.drivingDirection;
  if (data.drivingDirection === "FORWARD") {
    drivingDirectionButton.style.color = "green";
  } else {
    drivingDirectionButton.style.color = "red";
  }
  currentStageElement.innerText = data.currentStage;

  latestDriveCommandElement.innerText = data.latestDriveCommand;
  latestGantryCommandElement.innerText = data.latestGantryCommand;
  rcControlModeElement.innerText = data.rcControlMode;
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

