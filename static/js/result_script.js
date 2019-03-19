function fixUpTestSelection(source) {

    // Toggling the "failed_all" checkbox should apply to all failed test checkboxes
    failed_auto = false;
    if (source.id == "failed_all") {
        fail_checkboxes = document.getElementsByClassName("failed");

        for (var i = 0, n = fail_checkboxes.length; i < n; i++) {
            fail_checkboxes[i].checked = source.checked;

            if (fail_checkboxes[i].className.includes("auto")) {
                failed_auto = true;
            }
        }
    }

    // Toggling any "auto_" checkbox should apply to all "auto" tests because they can't be run individually at the moment
    if (failed_auto || source.className.includes("auto")) {
        auto_all = document.getElementById("auto_all");

        auto_all.checked = source.checked;
        auto_checkboxes = document.getElementsByClassName("auto");

        for(var i = 0, n = auto_checkboxes.length; i < n; i++ ) {
            auto_checkboxes[i].checked = auto_all.checked;
        }
    }

    // If any failed test checkbox is now unchecked, the "failed_all" checkbox should be too
    fail_all = 0 != fail_checkboxes.length;
    fail_checkboxes = document.getElementsByClassName("failed");
    for (var i = 0, n = fail_checkboxes.length; i < n; i++) {
        if (!fail_checkboxes[i].checked) {
            fail_all = false;
            break;
        }
    }
    document.getElementById("failed_all").checked = fail_all;
}

document.addEventListener("DOMContentLoaded", function() {
    fail_checkboxes = document.getElementsByClassName("failed");
    if (fail_checkboxes.length == 0) {
        document.getElementById("failed_all").disabled = true;
        document.getElementById("failed_all_label").style.opacity = 0.5;
    }
});
