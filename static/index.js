const minH = document.getElementById("minH")
const maxH = document.getElementById("maxH")
const minS = document.getElementById("minS")
const maxS = document.getElementById("maxS")
const minV = document.getElementById("minV")
const maxV = document.getElementById("maxV")

const loadSettings = () => {
    console.log("Loading settings...")
    fetch("/settings")
        .then(response => response.json())
        .then(data => {
            minH.value = data.minH
            maxH.value = data.maxH
            minS.value = data.minS
            maxS.value = data.maxS
            minV.value = data.minV
            maxV.value = data.maxV
        })
        .then(() => {
            minH.addEventListener("change", handleChange)
            maxH.addEventListener("change", handleChange)
            minS.addEventListener("change", handleChange)
            maxS.addEventListener("change", handleChange)
            minV.addEventListener("change", handleChange)
            maxV.addEventListener("change", handleChange) 
        })
}

const getTemperature = () => {
    fetch("/temperature")
        .then(response => response.json())
        .then(data => {
            document.getElementById("temperature").innerText = data.temperature
        })
}

window.addEventListener("load", loadSettings)
window.addEventListener("load", () => {
    getTemperature()
    setInterval(() => {
        getTemperature()
    }, 2000);
})

const handleChange = () => {
    
    const settingsJson = {
        minH: minH.value,
        maxH: maxH.value,
        minS: minS.value,
        maxS: maxS.value,
        minV: minV.value,
        maxV: maxV.value
    }

    const settingsJsonStr = JSON.stringify(settingsJson)

    fetch("/settings", {
        method: "POST",
        body: settingsJsonStr,
        headers: {
            "Content-Type": "application/json"
        }
    })

}