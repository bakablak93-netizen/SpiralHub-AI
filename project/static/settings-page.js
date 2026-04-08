(function () {
  "use strict";
  var sel = document.getElementById("settings-lang-select");
  if (!sel) return;
  sel.addEventListener("change", function () {
    var v = sel.value;
    if (!v) return;
    var hdr = { "Content-Type": "application/json", Accept: "application/json" };
    if (typeof window.csrfHeaders === "function") {
      hdr = window.csrfHeaders(hdr);
    }
    fetch(
      window.SETTINGS_LANG_URL || "/settings/lang",
      {
        method: "POST",
        headers: hdr,
        credentials: "same-origin",
        body: JSON.stringify({ lang: v }),
      }
    )
      .then(function (r) {
        if (!r.ok) throw new Error("lang");
        window.location.reload();
      })
      .catch(function () {
        window.location.reload();
      });
  });

  var themeInputs = document.querySelectorAll('input[name="theme"]');
  themeInputs.forEach(function (inp) {
    inp.addEventListener("change", function () {
      if (inp.checked) {
        document.documentElement.setAttribute("data-theme", inp.value);
      }
    });
  });

  var fontInputs = document.querySelectorAll('input[name="font_scale"]');
  fontInputs.forEach(function (inp) {
    inp.addEventListener("change", function () {
      if (inp.checked) {
        document.documentElement.setAttribute("data-font", inp.value);
      }
    });
  });
})();
