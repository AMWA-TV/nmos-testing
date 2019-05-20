function makeTableHeadersSticky() {
    offset = 0;
    thead_rows = document.getElementsByClassName("table")[0].tHead.children;
    for (var i = 0, n = thead_rows.length; i < n; i++) {
        tr_offset = 0;
        tr_cols = thead_rows[i].children;
        for (var j = 0, m = tr_cols.length; j < m; j++) {
            tr_cols[j].style.position = "sticky";
            tr_cols[j].style.top = offset + "px";

            if (tr_offset < tr_cols[j].offsetHeight) {
                tr_offset = tr_cols[j].offsetHeight;
            }
            // relying on no margins and no borders in the stylesheet to avoid issues like
            // https://github.com/w3c/csswg-drafts/issues/3136
        }
        offset += tr_offset;
    }
}

function changeTestSelection(source) {

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

    test_any = false;
    test_checkboxes = document.getElementsByName("test_selection");
    for (var i = 0, n = test_checkboxes.length; i < n; i++) {
        if (test_checkboxes[i].checked) {
            test_any = true;
            break;
        }
    }
    document.getElementById("runbtn").disabled = !test_any;
}

function disableRunbtn() {
    var runbtn = document.getElementById("runbtn");
    runbtn.value = "Executing tests...";
    runbtn.disabled = true;
}

document.addEventListener("DOMContentLoaded", function() {
    fail_checkboxes = document.getElementsByClassName("failed");
    if (fail_checkboxes.length == 0) {
        document.getElementById("failed_all").disabled = true;
        document.getElementById("failed_all_label").style.opacity = 0.5;
    }

    document.getElementById("runbtn").disabled = true;

    var json_file = new Blob([document.getElementById("json-results").textContent], {type: 'application/json'});
    var file_url = URL.createObjectURL(json_file);
    var download_link = document.getElementById("download");
    download_link.href = file_url;
    download_link.download = 'results.json';

    makeTableHeadersSticky();
    document.addEventListener("onresize", makeTableHeadersSticky);
});
