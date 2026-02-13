/**
 * DAX Noob — Lazy image optimization
 * Adds lazy loading, async decoding, and retry logic for images.
 */

// Add loading="lazy" and decoding="async" to all images
function optimizeImages() {
  var images = document.querySelectorAll("img");
  images.forEach(function (img) {
    if (!img.hasAttribute("loading")) {
      img.setAttribute("loading", "lazy");
    }
    if (!img.hasAttribute("decoding")) {
      img.setAttribute("decoding", "async");
    }
    // Prioritize images already in viewport
    var rect = img.getBoundingClientRect();
    if (rect.top < window.innerHeight && rect.bottom > 0) {
      img.setAttribute("fetchpriority", "high");
    }
  });
}

document.addEventListener("DOMContentLoaded", optimizeImages);

// Handle instant navigation — re-optimize images after page change
if (typeof document$ !== "undefined") {
  document$.subscribe(function () {
    optimizeImages();
  });
}

// Image retry logic — retry loading failed images (not 404s)
function setupImageRetry() {
  var MAX_RETRIES = 3;
  var RETRY_DELAY = 1000;
  var checked404s = {};

  function is404(url, callback) {
    if (checked404s[url]) { callback(true); return; }
    var xhr = new XMLHttpRequest();
    xhr.open("HEAD", url, true);
    xhr.onload = function () {
      if (xhr.status === 404) {
        checked404s[url] = true;
        callback(true);
      } else {
        callback(false);
      }
    };
    xhr.onerror = function () { callback(false); };
    xhr.send();
  }

  var allImages = document.querySelectorAll("img");
  allImages.forEach(function (img) {
    if (img.dataset.hasErrorHandler) return;
    img.dataset.hasErrorHandler = "true";

    var retryCount = 0;
    img.addEventListener("error", function () {
      var originalSrc = img.dataset.originalSrc || img.src.split("?")[0];
      img.dataset.originalSrc = originalSrc;

      is404(originalSrc, function (notFound) {
        if (notFound) {
          img.style.opacity = "0.3";
          img.style.border = "1px dashed var(--md-default-fg-color--lightest)";
          return;
        }
        if (retryCount < MAX_RETRIES) {
          retryCount++;
          setTimeout(function () {
            img.src = originalSrc + "?t=" + Date.now();
          }, RETRY_DELAY * retryCount);
        }
      });
    });

    img.addEventListener("load", function () {
      retryCount = 0;
      img.style.border = "";
      img.style.opacity = "";
    });
  });
}

document.addEventListener("DOMContentLoaded", setupImageRetry);

if (typeof document$ !== "undefined") {
  document$.subscribe(function () {
    setupImageRetry();
  });
}
