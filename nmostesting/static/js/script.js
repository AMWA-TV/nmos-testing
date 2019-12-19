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
        if (apiKey in specData[specKey]["apis"]) {
          label.innerHTML = specData[specKey]["apis"][apiKey]["name"] + ":";
        } else {
          label.innerHTML = "";
        }
        div.style.display = "block";
        var fields = ["host", "port", "version"];
        for (var i=0; i<fields.length; i++) {
          if ("disable_fields" in testData["specs"][apiNum] && testData["specs"][apiNum]["disable_fields"].indexOf(fields[i]) !== -1) {
            document.getElementById("endpoints-" + apiNum.toString() + "-" + fields[i] + "-save").value = document.getElementById("endpoints-" + apiNum.toString() + "-" + fields[i]).value;
            document.getElementById("endpoints-" + apiNum.toString() + "-" + fields[i]).disabled = true;
            document.getElementById("endpoints-" + apiNum.toString() + "-" + fields[i]).value = "";
          } else if (document.getElementById("endpoints-" + apiNum.toString() + "-" + fields[i]).disabled === true){
            document.getElementById("endpoints-" + apiNum.toString() + "-" + fields[i]).disabled = false;
            document.getElementById("endpoints-" + apiNum.toString() + "-" + fields[i]).value = document.getElementById("endpoints-" + apiNum.toString() + "-" + fields[i] + "-save").value;
          }
        }
      } else {
        div.style.display = "none";
      }
    }

    // Update the test selection dropdown
    var testDropdown = document.getElementById("test_selection");
    testDropdown.options.length = 0;
    for (var i=0; i<testData["test_methods"].length; i++) {
      testDropdown.options[i] = new Option(testData["test_descriptions"][i], testData["test_methods"][i]);
    }
}

function loadSettings() {
    try {
        if (typeof(sessionStorage) !== "undefined") {
            if (sessionStorage.getItem("test") !== null) {
                document.getElementById("test").value = sessionStorage.getItem("test");
                updateDropdown();

                var selectedOptions;
                try {
                    selectedOptions = JSON.parse(sessionStorage.getItem("test_selection"));
                }
                catch (e) {
                    selectedOptions = [sessionStorage.getItem("test_selection")];
                }
                var testOptions = document.getElementById("test_selection").options;
                for (var i = 0, n = testOptions.length; i < n; i++) {
                    testOptions[i].selected = selectedOptions.includes(testOptions[i].value);
                }

                var maxOptions = document.getElementById('hidden_options').value;
                for (var apiNum=0; apiNum<maxOptions; apiNum++) {
                    document.getElementById("endpoints-" + apiNum.toString() + "-host").value = sessionStorage.getItem("endpoints-" + apiNum.toString() + "-host");
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
    document.getElementById("test_selection").selectedIndex = 0;
}

function saveSettings() {
    try {
        if (typeof(sessionStorage) !== "undefined") {
            sessionStorage.setItem("test", document.getElementById("test").value);

            var selectedOptions = []
            var testOptions = document.getElementById("test_selection").options;
            for (var i = 0, n = testOptions.length; i < n; i++) {
                if (testOptions[i].selected) {
                    selectedOptions.push(testOptions[i].value);
                }
            }
            sessionStorage.setItem("test_selection", JSON.stringify(selectedOptions));

            var maxOptions = document.getElementById('hidden_options').value;
            for (var apiNum=0; apiNum<maxOptions; apiNum++) {
                sessionStorage.setItem("endpoints-" + apiNum.toString() + "-host", document.getElementById("endpoints-" + apiNum.toString() + "-host").value);
                sessionStorage.setItem("endpoints-" + apiNum.toString() + "-port", document.getElementById("endpoints-" + apiNum.toString() + "-port").value);
                sessionStorage.setItem("endpoints-" + apiNum.toString() + "-version", document.getElementById("endpoints-" + apiNum.toString() + "-version").value);
            }
        }
    }
    catch (e) {
        console.log("Error using sessionStorage.");
    }
};

function disableRunbtn() {
    var runbtn = document.getElementById("runbtn");
    runbtn.value = "Executing tests...";
    runbtn.disabled = true;
}

document.addEventListener("DOMContentLoaded", function() {
    document.getElementById("test").onchange = function() {
        updateDropdown();
        document.getElementById("test_selection").selectedIndex = 0;
    }

    document.getElementById("test_selection").onchange = function(event) {

        // Prohibit "all" and individual test cases being selected
        testOptions = document.getElementById("test_selection").options;
        if (event.target.value == "all") {
            for (var i = 1, n = testOptions.length; i < n; i++) {
                testOptions[i].selected = false;
            }
        }
        else {
            testOptions[0].selected = false;
        }

        test_any = false;
        for (var i = 0, n = testOptions.length; i < n; i++) {
            if (testOptions[i].selected) {
                test_any = true;
                break;
            }
        }
        document.getElementById("runbtn").disabled = !test_any;
    }

    loadSettings();
});
