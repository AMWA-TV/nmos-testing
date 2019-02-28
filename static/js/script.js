function updateDropdown() {
    var testDropdown = document.getElementById("test");
    var testID = testDropdown.options[testDropdown.selectedIndex].value;

    var testData = JSON.parse(document.getElementById('hidden_tests').value)[testID];
    var specData = JSON.parse(document.getElementById('hidden_specs').value);
    var maxOptions = document.getElementById('hidden_options').value;

    // Update the version dropdown
    for (var apiNum=0; apiNum<maxOptions; apiNum++) {
      var div = document.getElementById("endpoints-" + apiNum.toString());

      if (apiNum < testData["specs"].length) {
        var label = document.getElementById("endpoints-" + apiNum.toString() + "-label");
        var versionDropdown = document.getElementById("endpoints-" + apiNum.toString() + "-version");
        versionDropdown.options.length = 0;
        var specKey = testData["specs"][apiNum]["spec_key"];
        var apiKey = testData["specs"][apiNum]["api_key"];
        for (var i=0; i<specData[specKey]["versions"].length; i++) {
          versionDropdown.options[i] = new Option(specData[specKey]["versions"][i], specData[specKey]["versions"][i]);
        }
        versionDropdown.value = specData[specKey]["default_version"];
        label.innerHTML = specData[specKey]["apis"][apiKey]["name"] + ":";
        div.style.display = "block";
      } else {
        div.style.display = "none";
      }
    }

    // Update the test selection dropdown
    var testDropdown = document.getElementById("test_selection");
    testDropdown.options.length = 0;
    for (var i=0; i<testData["tests"].length; i++) {
      testDropdown.options[i] = new Option(testData["tests"][i], testData["tests"][i]);
    }
}

function loadSettings() {
    try {
        if (typeof(sessionStorage) !== "undefined") {
            if (sessionStorage.getItem("test") !== null) {
                document.getElementById("test").value = sessionStorage.getItem("test");
                updateDropdown();
                document.getElementById("test_selection").value = sessionStorage.getItem("test_selection");
                var maxOptions = document.getElementById('hidden_options').value;
                for (var apiNum=0; apiNum<maxOptions; apiNum++) {
                    document.getElementById("endpoints-" + apiNum.toString() + "-ip").value = sessionStorage.getItem("endpoints-" + apiNum.toString() + "-ip");
                    document.getElementById("endpoints-" + apiNum.toString() + "-port").value = sessionStorage.getItem("endpoints-" + apiNum.toString() + "-port");
                    document.getElementById("endpoints-" + apiNum.toString() + "-version").value = sessionStorage.getItem("endpoints-" + apiNum.toString() + "-version");
                }
                return;
            }
        }
    }
    catch (e) {
        console.log("Error using sessionStorage.");
    }
    updateDropdown();
}

function saveSettings() {
    try {
        if (typeof(sessionStorage) !== "undefined") {
            sessionStorage.setItem("test", document.getElementById("test").value);
            sessionStorage.setItem("test_selection", document.getElementById("test_selection").value);
            var maxOptions = document.getElementById('hidden_options').value;
            for (var apiNum=0; apiNum<maxOptions; apiNum++) {
                sessionStorage.setItem("endpoints-" + apiNum.toString() + "-ip", document.getElementById("endpoints-" + apiNum.toString() + "-ip",).value);
                sessionStorage.setItem("endpoints-" + apiNum.toString() + "-port", document.getElementById("endpoints-" + apiNum.toString() + "-port",).value);
                sessionStorage.setItem("endpoints-" + apiNum.toString() + "-version", document.getElementById("endpoints-" + apiNum.toString() + "-version",).value);
            }
        }
    }
    catch (e) {
        console.log("Error using sessionStorage.");
    }
};

document.addEventListener("DOMContentLoaded", function() {
    document.getElementById("test").onchange = function() {
        updateDropdown();
    }
    loadSettings();
});
