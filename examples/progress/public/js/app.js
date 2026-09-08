/* Progress demo — theme toggle + nav current page. */
(function () {
  var root = document.documentElement;
  var KEY = "almasix-theme";

  function apply(theme) {
    root.setAttribute("data-theme", theme);
    var btn = document.getElementById("theme-toggle");
    if (btn) {
      var next = theme === "dark" ? "light" : "dark";
      btn.setAttribute("aria-label", "Switch to " + next + " mode");
      btn.setAttribute("title", "Switch to " + next + " mode");
    }
  }

  function current() {
    return root.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  var btn = document.getElementById("theme-toggle");
  if (btn) {
    btn.addEventListener("click", function () {
      var next = current() === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(KEY, next);
      } catch (e) {}
      apply(next);
    });
    apply(current());
  }

  var path = window.location.pathname.replace(/\/$/, "") || "/";
  document.querySelectorAll(".nav-links a[href]").forEach(function (link) {
    var href = link.getAttribute("href") || "";
    var clean = href.replace(/\/$/, "") || "/";
    if (clean === path) {
      link.setAttribute("aria-current", "page");
    }
  });
})();
