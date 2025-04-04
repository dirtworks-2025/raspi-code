const temperatureElement = document.getElementById("temperature");
const controlsContainer = document.getElementById("controls");
const frontCameraElement = document.getElementById("frontCamera");
const rearCameraElement = document.getElementById("rearCamera");

const frontDriveCmdElement = document.getElementById("frontDriveCmd");
const frontHoeCmdElement = document.getElementById("frontHoeCmd");
const frontLostContextElement = document.getElementById("frontLostContext");
const rearDriveCmdElement = document.getElementById("rearDriveCmd");
const rearHoeCmdElement = document.getElementById("rearHoeCmd");
const rearLostContextElement = document.getElementById("rearLostContext");

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
  if (data.front) {
    frontCameraElement.src = data.front.combinedFrameJpgTxt;
    frontDriveCmdElement.innerText = data.front.driveCmd;
    frontHoeCmdElement.innerText = data.front.hoeCmd;
    if (data.front.lostContext) {
      frontLostContextElement.innerText = "Lost Context";
    } else {
      frontLostContextElement.innerText = "";
    }
  }
  if (data.rear) {
    rearCameraElement.src = data.rear.combinedFrameJpgTxt;
    rearDriveCmdElement.innerText = data.rear.driveCmd;
    rearHoeCmdElement.innerText = data.rear.hoeCmd;
    if (data.rear.lostContext) {
      rearLostContextElement.innerText = "Lost Context";
    } else {
      rearLostContextElement.innerText = "";
    }
  }
});

window.addEventListener("load", () => {
  loadSettings();
});
