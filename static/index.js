const minSat = document.getElementById("minSat")
const maxSat = document.getElementById("maxSat")

const handleChange = () => {
    const minSatVal = minSat.value
    const maxSatVal = maxSat.value
    
    const settingsJson = {
        minSat: minSatVal,
        maxSat: maxSatVal,
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

minSat.addEventListener("change", handleChange)
maxSat.addEventListener("change", handleChange)