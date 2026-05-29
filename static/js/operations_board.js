// Operations & Audit Defense Board.
//
// A persistent right-hand panel that shows a "system summary" by default and
// swaps to a facility or move detail when a card/token/ticker item is clicked.
// Detail content is pre-rendered server-side into hidden
// [data-ops-detail="<kind>-<id>"] sources; we just copy innerHTML, mirroring
// the live_route_map.js drawer pattern but keeping the panel always visible.
(function () {
  function sourceFor(board, key) {
    return board.querySelector('[data-ops-detail="' + key + '"]');
  }

  function showPanel(board, key) {
    var content = board.querySelector("[data-ops-panel-content]");
    var source = key ? sourceFor(board, key) : null;
    if (!content || !source) return false;
    content.innerHTML = source.innerHTML;
    return true;
  }

  function setActive(board, element) {
    board
      .querySelectorAll(".opsb-facility.active, .opsb-token.active")
      .forEach(function (node) {
        node.classList.remove("active");
      });
    if (element) element.classList.add("active");
  }

  function showHome(board) {
    setActive(board, null);
    showPanel(board, "global");
  }

  function bindBoard(board) {
    showHome(board);

    board.addEventListener("click", function (event) {
      var home = event.target.closest("[data-ops-home]");
      if (home && board.contains(home)) {
        event.preventDefault();
        showHome(board);
        return;
      }

      var trigger = event.target.closest("[data-ops-open]");
      if (!trigger || !board.contains(trigger)) return;

      var key =
        trigger.getAttribute("data-ops-open") +
        "-" +
        trigger.getAttribute("data-ops-id");
      if (showPanel(board, key)) {
        event.preventDefault();
        setActive(board, trigger.closest(".opsb-facility, .opsb-token"));
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-ops-board]").forEach(bindBoard);
  });
})();
