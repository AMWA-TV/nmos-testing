function updateDropdown() {
    var hiddenData = JSON.parse(document.getElementById('hidden').value);

    var testDropdown = document.getElementById("test");
    var testID = testDropdown.options[testDropdown.selectedIndex].value;

    var testData = hiddenData[testID];

    // Update the version dropdown
    var versionDropdown = document.getElementById("version");
    versionDropdown.options.length = 0;
    for (var i=0; i<testData["versions"].length; i++) {
      versionDropdown.options[i] = new Option(testData["versions"][i], testData["versions"][i]);
    }
    versionDropdown.value = testData["default_version"];

    // Update the input boxes and their labels
    var input1 = document.getElementById("input1");
    var input2 = document.getElementById("input2");
    var secAPI = document.getElementById("secondary_api");
    if (testData["input_labels"].length == 1) {
      input1.innerHTML = testData["input_labels"][0] + ":";
      input2.innerHTML = "";
      secAPI.style.display = "none";
    } else {
      input1.innerHTML = testData["input_labels"][0] + ":";
      input2.innerHTML = testData["input_labels"][1] + ":";
      secAPI.style.display = "block";
    }
}

document.addEventListener("DOMContentLoaded", function() {
    document.getElementById("test").onchange = function() {
        updateDropdown();
    }

    updateDropdown();
});
