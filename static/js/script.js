function updateDropdown() {
    var hiddenData = JSON.parse(document.getElementById('hidden').value);
    var maxVersions = hiddenData['max_versions']

    var testDropdown = document.getElementById("test");
    var testID = testDropdown.options[testDropdown.selectedIndex].value;

    var testData = hiddenData[testID];

    // Update the version dropdown
    for (var apiNum=0; apiNum<maxVersions; apiNum++){
      var versionDropdown = document.getElementById("versions-" + apiNum.toString() + "-version");
      versionDropdown.options.length = 0;
      if (apiNum < testData["specs"].length){
        for (var i=0; i<testData["specs"][apiNum]["versions"].length; i++) {
          versionDropdown.options[i] = new Option(testData["specs"][apiNum]["versions"][i], testData["specs"][apiNum]["versions"][i]);
        }
        versionDropdown.style.display = "block";
        versionDropdown.value = testData["specs"][apiNum]["default_version"];
        var label = testData["specs"][apiNum]["spec_key"].toUpperCase() + " Version: ";
        versionDropdown.labels[0].innerText = label;
        versionDropdown.labels[0].style.display = "block";
      }else{
        versionDropdown.style.display = "none";
        versionDropdown.labels[0].style.display = "none";
      }      
    }

    // Update the input boxes and their labels
    var input1 = document.getElementById("input1");
    var input2 = document.getElementById("input2");
    var secAPI = document.getElementById("secondary_api");
    if (testData['specs'][0]["input_labels"].length == 1) {
      input1.innerHTML = testData['specs'][0]["input_labels"][0] + ":";
      input2.innerHTML = "";
      secAPI.style.display = "none";
    } else {
      input1.innerHTML = testData['specs'][0]["input_labels"][0] + ":";
      input2.innerHTML = testData['specs'][0]["input_labels"][1] + ":";
      secAPI.style.display = "block";
    }

    // Update the test selection dropdown
    var testDropdown = document.getElementById("test_selection");
    testDropdown.options.length = 0;
    for (var i=0; i<testData["tests"].length; i++) {
      testDropdown.options[i] = new Option(testData["tests"][i], testData["tests"][i]);
    }
}

document.addEventListener("DOMContentLoaded", function() {
    document.getElementById("test").onchange = function() {
        updateDropdown();
    }

    updateDropdown();
});
