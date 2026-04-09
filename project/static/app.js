(function () {
  "use strict";

  /* ——— Мобильное меню ——— */
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("main-nav");
  var overlay = document.querySelector(".nav-overlay");
  var mqNav = window.matchMedia("(max-width: 768px)");
  var savedScrollY = 0;
  var scrollLocked = false;

  function lockScroll() {
    if (!mqNav.matches) return;
    savedScrollY = window.scrollY || document.documentElement.scrollTop || 0;
    document.body.style.position = "fixed";
    document.body.style.top = "-" + savedScrollY + "px";
    document.body.style.left = "0";
    document.body.style.right = "0";
    document.body.style.width = "100%";
    scrollLocked = true;
  }

  function unlockScroll() {
    if (!scrollLocked) return;
    document.body.style.position = "";
    document.body.style.top = "";
    document.body.style.left = "";
    document.body.style.right = "";
    document.body.style.width = "";
    window.scrollTo(0, savedScrollY);
    scrollLocked = false;
  }

  if (toggle && nav) {
    function closeNav() {
      unlockScroll();
      document.body.classList.remove("nav-open");
      document.documentElement.classList.remove("nav-open");
      toggle.setAttribute("aria-expanded", "false");
    }
    function openNav() {
      document.body.classList.add("nav-open");
      document.documentElement.classList.add("nav-open");
      toggle.setAttribute("aria-expanded", "true");
      lockScroll();
    }
    toggle.addEventListener("click", function () {
      if (document.body.classList.contains("nav-open")) closeNav();
      else openNav();
    });
    if (overlay) overlay.addEventListener("click", closeNav);
    nav.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", function () {
        if (mqNav.matches) closeNav();
      });
    });
    window.addEventListener("resize", function () {
      if (!mqNav.matches && document.body.classList.contains("nav-open")) {
        closeNav();
      }
    });
  }

  /* ——— Фильтры витрины (главная / каталог) ——— */
  var sfToggle = document.querySelector(".storefront-filters-toggle");
  var sfPanel = document.getElementById("storefront-filters-panel");
  if (sfPanel && window.matchMedia("(min-width: 769px)").matches) {
    sfPanel.classList.add("is-open");
  }
  if (sfToggle && sfPanel) {
    sfToggle.addEventListener("click", function () {
      var open = sfPanel.classList.toggle("is-open");
      sfToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  /* ——— Фильтры продавцов ——— */
  var selToggle = document.querySelector(".sellers-filters-toggle");
  var selPanel = document.getElementById("sellers-filters-panel");
  if (selPanel && window.matchMedia("(min-width: 769px)").matches) {
    selPanel.classList.add("is-open");
  }
  if (selToggle && selPanel) {
    selToggle.addEventListener("click", function () {
      var open = selPanel.classList.toggle("is-open");
      selToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  /* ——— Микрокредит: пошаговая форма ——— */
  var wiz = document.getElementById("credit-wizard");
  if (wiz) {
    var steps = wiz.querySelectorAll(".credit-wiz-step");
    var bar = document.querySelector(".credit-wiz-bar");
    var btnPrev = document.querySelector(".credit-wiz-prev");
    var btnNext = document.querySelector(".credit-wiz-next");
    var btnSubmit = document.querySelector(".credit-wiz-submit");
    var cur = 0;

    function showStep(i) {
      cur = Math.max(0, Math.min(i, steps.length - 1));
      steps.forEach(function (s, j) {
        s.hidden = j !== cur;
        s.classList.toggle("is-active", j === cur);
      });
      if (btnPrev) btnPrev.hidden = cur === 0;
      if (btnNext) btnNext.hidden = cur === steps.length - 1;
      if (btnSubmit) btnSubmit.hidden = cur !== steps.length - 1;
      if (bar) bar.setAttribute("data-step", String(cur + 1));
      if (cur === steps.length - 1 && typeof window.updateCreditSummary === "function") {
        window.updateCreditSummary();
      }
    }

    function validateCurrentStep() {
      var step = steps[cur];
      var ok = true;
      step.querySelectorAll("input, select, textarea").forEach(function (el) {
        if (!ok) return;
        if (!el.name || el.type === "button" || el.type === "submit") return;
        if (!el.checkValidity()) {
          el.reportValidity();
          ok = false;
        }
      });
      return ok;
    }

    var amountInput = document.getElementById("requested_amount");
    var amountRange = document.getElementById("credit_amount_range");
    if (amountInput && amountRange) {
      function syncRangeToInput() {
        amountInput.value = amountRange.value;
      }
      function syncInputToRange() {
        var v = parseInt(amountInput.value, 10) || 10000;
        v = Math.max(parseInt(amountRange.min, 10), Math.min(parseInt(amountRange.max, 10), v));
        amountRange.value = v;
        amountInput.value = v;
      }
      amountRange.addEventListener("input", syncRangeToInput);
      amountInput.addEventListener("change", syncInputToRange);
      syncInputToRange();
    }

    var loanMonths = document.getElementById("loan_term_months");
    var loanMonthsOut = document.getElementById("loan_term_out");
    if (loanMonths && loanMonthsOut) {
      loanMonths.addEventListener("input", function () {
        loanMonthsOut.textContent = loanMonths.value;
      });
      loanMonthsOut.textContent = loanMonths.value;
    }

    if (btnPrev) btnPrev.addEventListener("click", function () { showStep(cur - 1); });
    if (btnNext)
      btnNext.addEventListener("click", function () {
        if (!validateCurrentStep()) return;
        showStep(cur + 1);
      });

    var creditForm = document.getElementById("credit-form");
    if (window.matchMedia("(min-width: 769px)").matches && steps.length) {
      steps.forEach(function (s) {
        s.hidden = false;
      });
      if (btnPrev) btnPrev.hidden = true;
      if (btnNext) btnNext.hidden = true;
      if (btnSubmit) btnSubmit.hidden = false;
      if (bar) bar.style.display = "none";
      if (typeof window.updateCreditSummary === "function") window.updateCreditSummary();
      if (creditForm) {
        creditForm.addEventListener(
          "input",
          function () {
            if (typeof window.updateCreditSummary === "function") window.updateCreditSummary();
          },
          true
        );
      }
    } else {
      showStep(0);
    }
  }

})();
