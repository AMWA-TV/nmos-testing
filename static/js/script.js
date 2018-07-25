document.addEventListener("DOMContentLoaded", function() {
    document.getElementById("test").onchange = function() {
        if(this.selectedIndex == 1) { document.getElementById('version_select').style.display = "none"; }
        else { document.getElementById('version_select').style.display = "inline"; }
    }
});