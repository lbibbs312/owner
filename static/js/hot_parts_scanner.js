/* hot_parts_scanner.js -- inline barcode scanner for transfer line inputs.
 *
 * Public API:
 *   HotPartsScanner.attachScanner(buttonSelector)
 *     - Wires every element matching `buttonSelector` to open a modal
 *       with the device's rear camera. When a barcode is detected, its
 *       rawValue is written into the element identified by the button's
 *       `data-target` attribute (a CSS selector for an <input>).
 *
 * Falls back gracefully if BarcodeDetector is unavailable.
 * No external library dependencies.
 */
(function (global) {
  "use strict";

  var modalEl = null;
  var videoEl = null;
  var statusEl = null;
  var closeBtn = null;
  var activeStream = null;
  var activeTargetSelector = null;
  var detectionTimer = null;
  var detector = null;
  var supported = (typeof window !== "undefined") && ("BarcodeDetector" in window);

  function ensureModal() {
    if (modalEl) return modalEl;
    modalEl = document.createElement("div");
    modalEl.id = "hotPartsScannerModal";
    modalEl.style.cssText = [
      "position:fixed", "top:0", "left:0", "width:100vw", "height:100vh",
      "background:rgba(0,0,0,0.85)", "z-index:5000", "display:none",
      "flex-direction:column", "align-items:center", "justify-content:center",
      "padding:1rem"
    ].join(";");

    var inner = document.createElement("div");
    inner.style.cssText = "max-width:480px;width:100%;background:#fff;border-radius:8px;padding:1rem;text-align:center;";

    var title = document.createElement("h5");
    title.textContent = "Scan part number";
    title.style.marginTop = "0";
    inner.appendChild(title);

    videoEl = document.createElement("video");
    videoEl.setAttribute("playsinline", "");
    videoEl.setAttribute("muted", "");
    videoEl.style.cssText = "width:100%;max-height:60vh;background:#000;border-radius:4px;";
    inner.appendChild(videoEl);

    statusEl = document.createElement("p");
    statusEl.style.cssText = "margin:0.75rem 0 0;font-size:0.9rem;color:#555;";
    statusEl.textContent = supported
      ? "Point the rear camera at the barcode."
      : "Scanner not supported on this device — please enter manually.";
    inner.appendChild(statusEl);

    closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "btn btn-secondary";
    closeBtn.style.cssText = "margin-top:0.75rem;";
    closeBtn.textContent = "Close";
    closeBtn.addEventListener("click", closeScanner);
    inner.appendChild(closeBtn);

    modalEl.appendChild(inner);
    document.body.appendChild(modalEl);
    modalEl.addEventListener("click", function (e) {
      if (e.target === modalEl) closeScanner();
    });
    return modalEl;
  }

  function stopStream() {
    if (detectionTimer) {
      clearInterval(detectionTimer);
      detectionTimer = null;
    }
    if (activeStream) {
      try {
        activeStream.getTracks().forEach(function (t) { t.stop(); });
      } catch (e) { /* ignore */ }
      activeStream = null;
    }
    if (videoEl) {
      try { videoEl.pause(); } catch (e) { /* ignore */ }
      videoEl.srcObject = null;
    }
  }

  function closeScanner() {
    stopStream();
    if (modalEl) modalEl.style.display = "none";
    activeTargetSelector = null;
  }

  function writeResultToTarget(value) {
    if (!activeTargetSelector || !value) return;
    var input = document.querySelector(activeTargetSelector);
    if (input) {
      input.value = value;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
      try { input.focus(); } catch (e) { /* ignore */ }
    }
    closeScanner();
  }

  function startDetection() {
    if (!supported) return;
    try {
      detector = detector || new window.BarcodeDetector();
    } catch (e) {
      if (statusEl) statusEl.textContent = "Scanner failed to initialize — please enter manually.";
      return;
    }
    detectionTimer = setInterval(function () {
      if (!videoEl || videoEl.readyState < 2) return;
      detector.detect(videoEl).then(function (codes) {
        if (codes && codes.length) {
          var raw = codes[0].rawValue || codes[0].rawData || "";
          if (raw) writeResultToTarget(String(raw).trim());
        }
      }).catch(function () { /* keep trying */ });
    }, 350);
  }

  function openScanner(targetSelector) {
    ensureModal();
    activeTargetSelector = targetSelector || null;
    modalEl.style.display = "flex";
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      statusEl.textContent = "Camera not available — please enter manually.";
      return;
    }
    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } })
      .then(function (stream) {
        activeStream = stream;
        videoEl.srcObject = stream;
        return videoEl.play();
      })
      .then(function () {
        if (supported) startDetection();
      })
      .catch(function () {
        statusEl.textContent = "Cannot access camera — please enter manually.";
      });
  }

  function attachScanner(buttonSelector) {
    var nodes = document.querySelectorAll(buttonSelector);
    Array.prototype.forEach.call(nodes, function (btn) {
      if (btn.dataset.scannerBound === "1") return;
      btn.dataset.scannerBound = "1";
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        openScanner(btn.getAttribute("data-target"));
      });
    });
  }

  global.HotPartsScanner = {
    attachScanner: attachScanner,
    openScanner: openScanner,
    closeScanner: closeScanner,
    isSupported: function () { return supported; }
  };
})(typeof window !== "undefined" ? window : this);
