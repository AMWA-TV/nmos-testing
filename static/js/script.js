function updateDropdown() {
    var hiddenData = JSON.parse(document.getElementById('hidden').value);

    var testDropdown = document.getElementById("test");
    var testID = testDropdown.options[testDropdown.selectedIndex].value;

    var testData = hiddenData[testID];

    var versionDropdown = document.getElementById("version");
    versionDropdown.options.length = 0;
    for (var i=0; i<testData["versions"].length; i++) {
      versionDropdown.options[i] = new Option(testData["versions"][i], testData["versions"][i]);
    }
    versionDropdown.value = testData["default_version"];
}

document.addEventListener("DOMContentLoaded", function() {
    document.getElementById("test").onchange = function() {
        updateDropdown();
    }

    updateDropdown();
});
