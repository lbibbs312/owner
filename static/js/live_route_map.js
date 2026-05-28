(function () {
  function detailKey(kind, id) {
    return kind + "-" + id;
  }

  function closeDrawer(drawer) {
    if (!drawer) return;
    drawer.hidden = true;
    drawer.setAttribute("aria-hidden", "true");
    document.documentElement.classList.remove("route-map-drawer-open");
  }

  function openDrawer(shell, trigger) {
    var drawer = shell.querySelector("[data-route-map-drawer]");
    var content = shell.querySelector("[data-route-map-drawer-content]");
    if (!drawer || !content) return false;

    var kind = trigger.getAttribute("data-route-map-open");
    var id = trigger.getAttribute("data-route-map-id");
    var source = shell.querySelector('[data-route-map-detail="' + detailKey(kind, id) + '"]');
    if (!source) return false;

    content.innerHTML = source.innerHTML;
    drawer.hidden = false;
    drawer.setAttribute("aria-hidden", "false");
    document.documentElement.classList.add("route-map-drawer-open");
    var close = drawer.querySelector("[data-route-map-close]");
    if (close) close.focus({ preventScroll: true });
    return true;
  }

  function bindShell(shell) {
    shell.addEventListener("click", function (event) {
      var close = event.target.closest("[data-route-map-close]");
      if (close) {
        event.preventDefault();
        closeDrawer(shell.querySelector("[data-route-map-drawer]"));
        return;
      }

      var trigger = event.target.closest("[data-route-map-open]");
      if (!trigger || !shell.contains(trigger)) return;
      if (openDrawer(shell, trigger)) {
        event.preventDefault();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-route-map-shell]").forEach(bindShell);
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    document.querySelectorAll("[data-route-map-drawer]:not([hidden])").forEach(closeDrawer);
  });
})();
