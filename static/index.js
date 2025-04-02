const temperatureEl = document.getElementById("temperature");
const controlsContainer = document.getElementById("controls");

const sliders = [
  { id: "minH", label: "Min. Hue", min: 0, max: 179 },
  { id: "maxH", label: "Max. Hue", min: 0, max: 179 },
  { id: "minS", label: "Min. Saturation", min: 0, max: 255 },
  { id: "maxS", label: "Max. Saturation", min: 0, max: 255 },
  { id: "minV", label: "Min. Value", min: 0, max: 255 },
  { id: "maxV", label: "Max. Value", min: 0, max: 255 },
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

        input.addEventListener("change", handleChange);
      });
      checkboxes.forEach(({ id }) => {
        const input = elements[id];
        input.checked = data[id];

        input.addEventListener("change", handleChange);
      });
    });
};

const getTemperature = () => {
  fetch("/temperature")
    .then((res) => res.json())
    .then((data) => {
      temperatureEl.innerText = data.temperature;
    });
};

const handleChange = () => {
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

window.addEventListener("load", () => {
  loadSettings();
  getTemperature();
  setInterval(getTemperature, 5000);
});
