const minH = document.getElementById("minH")
const maxH = document.getElementById("maxH")
const minS = document.getElementById("minS")
const maxS = document.getElementById("maxS")
const minV = document.getElementById("minV")
const maxV = document.getElementById("maxV")

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

minH.addEventListener("change", handleChange)
maxH.addEventListener("change", handleChange)
minS.addEventListener("change", handleChange)
maxS.addEventListener("change", handleChange)
minV.addEventListener("change", handleChange)
maxV.addEventListener("change", handleChange)