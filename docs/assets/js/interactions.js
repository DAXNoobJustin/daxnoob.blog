/**
 * DAX Noob — Interactions
 * Reading progress bar, scroll-reveal animations,
 * keyboard-accessible focus, and micro-interactions.
 */
(function () {
  "use strict";

  /* ------------------------------------------------
     1. Reading progress bar (blog posts only)
     ------------------------------------------------ */
  function initProgress() {
    var content = document.querySelector(".md-content--post .md-content__inner");
    if (!content) return;

    var bar = document.createElement("div");
    bar.className = "dn-progress";
    bar.setAttribute("role", "progressbar");
    bar.setAttribute("aria-label", "Reading progress");
    document.body.appendChild(bar);

    var ticking = false;
    function updateProgress() {
      if (!ticking) {
        window.requestAnimationFrame(function () {
          var docHeight = document.documentElement.scrollHeight - window.innerHeight;
          if (docHeight > 0) {
            var pct = Math.min((window.scrollY / docHeight) * 100, 100);
            bar.style.width = pct + "%";
            bar.setAttribute("aria-valuenow", Math.round(pct));
          }
          ticking = false;
        });
        ticking = true;
      }
    }

    window.addEventListener("scroll", updateProgress, { passive: true });
    updateProgress();
  }

  /* ------------------------------------------------
     2. Scroll-reveal for blog cards
     ------------------------------------------------ */
  function initReveal() {
    if (!("IntersectionObserver" in window)) return;

    var cards = document.querySelectorAll(".md-post--excerpt");
    if (!cards.length) return;

    cards.forEach(function (card, i) {
      card.style.opacity = "0";
      card.style.transform = "translateY(24px)";
      card.style.transition =
        "opacity 0.55s cubic-bezier(0.16,1,0.3,1) " +
        Math.min(i * 0.07, 0.35) + "s, " +
        "transform 0.55s cubic-bezier(0.16,1,0.3,1) " +
        Math.min(i * 0.07, 0.35) + "s";
    });

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.style.opacity = "1";
            entry.target.style.transform = "translateY(0)";
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.08, rootMargin: "0px 0px -40px 0px" }
    );

    cards.forEach(function (card) {
      observer.observe(card);
    });
  }

  /* ------------------------------------------------
     3. General section reveal (dn-reveal classes)
     ------------------------------------------------ */
  function initSectionReveal() {
    if (!("IntersectionObserver" in window)) return;

    var sections = document.querySelectorAll(".dn-reveal, .dn-reveal-stagger");
    if (!sections.length) return;

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("dn-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.1, rootMargin: "0px 0px -60px 0px" }
    );

    sections.forEach(function (el) {
      observer.observe(el);
    });
  }

  /* ------------------------------------------------
     4. Grid card tilt effect (about page cards)
     ------------------------------------------------ */
  function initCardTilt() {
    var gridCards = document.querySelectorAll(".grid.cards > ul > li, .grid.cards > ol > li");
    if (!gridCards.length) return;

    gridCards.forEach(function (card) {
      card.addEventListener("mousemove", function (e) {
        var rect = card.getBoundingClientRect();
        var x = (e.clientX - rect.left) / rect.width  - 0.5;
        var y = (e.clientY - rect.top)  / rect.height - 0.5;
        card.style.transform =
          "perspective(600px) rotateY(" + (x * 4) + "deg) rotateX(" + (-y * 4) + "deg) translateY(-2px)";
      });

      card.addEventListener("mouseleave", function () {
        card.style.transform = "";
        card.style.transition = "transform 0.4s cubic-bezier(0.16,1,0.3,1)";
        setTimeout(function () { card.style.transition = ""; }, 400);
      });
    });
  }

  /* ------------------------------------------------
     5. Keyboard-visible focus rings
     ------------------------------------------------ */
  function initFocusRing() {
    document.body.classList.add("dn-pointer");

    document.addEventListener("keydown", function (e) {
      if (e.key === "Tab") {
        document.body.classList.remove("dn-pointer");
        document.body.classList.add("dn-keyboard");
      }
    });

    document.addEventListener("mousedown", function () {
      document.body.classList.remove("dn-keyboard");
      document.body.classList.add("dn-pointer");
    });
  }

  /* ------------------------------------------------
     6. Smooth scroll-to-top button enhancement
     ------------------------------------------------ */
  function initScrollTop() {
    var btn = document.querySelector("[data-md-component='top']");
    if (!btn) return;

    btn.addEventListener("click", function (e) {
      e.preventDefault();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  /* ------------------------------------------------
     7. Bootstrap
     ------------------------------------------------ */
  function init() {
    initProgress();
    initReveal();
    initSectionReveal();
    initCardTilt();
    initFocusRing();
    initScrollTop();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Re-init on MkDocs Material instant navigation
  if (typeof document$ !== "undefined") {
    document$.subscribe(function () {
      var oldBar = document.querySelector(".dn-progress");
      if (oldBar) oldBar.remove();
      init();
    });
  }
})();
