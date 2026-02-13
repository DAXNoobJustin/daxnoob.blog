/**
 * Hero Image Scroll Effect
 * Fades the hero image from opacity 1 → 0 on scroll so it
 * disappears into the page background.
 */
(function () {
  "use strict";

  function initHeroScroll() {
    var hero = document.querySelector(".hero-banner");
    if (!hero) return;

    var image = hero.querySelector(".hero-banner__image");
    if (!image) return;

    var heroHeight = hero.offsetHeight;
    var ticking = false;
    var body = document.body;

    function onScroll() {
      if (!ticking) {
        window.requestAnimationFrame(function () {
          var scrollY = window.scrollY || window.pageYOffset;
          var progress = Math.min(scrollY / (heroHeight * 0.65), 1);

          // Image: opacity 1 → 0
          image.style.opacity = 1 - progress;

          // Toggle hero-scrolled once the user scrolls past 70% of the hero
          if (scrollY >= heroHeight * 0.7) {
            body.classList.add("hero-scrolled");
          } else {
            body.classList.remove("hero-scrolled");
          }

          ticking = false;
        });
        ticking = true;
      }
    }

    // Recalculate on resize
    window.addEventListener("resize", function () {
      heroHeight = hero.offsetHeight;
    });

    window.addEventListener("scroll", onScroll, { passive: true });

    // Run once on load in case page is already scrolled
    onScroll();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initHeroScroll);
  } else {
    initHeroScroll();
  }
})();
