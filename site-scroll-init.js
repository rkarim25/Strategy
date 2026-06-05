/** Run in <head> — suppress browser #hash anchor scroll on first paint and navigation. */
(function () {
  if ("scrollRestoration" in history) {
    history.scrollRestoration = "manual";
  }

  function scrollToTop() {
    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    if (document.documentElement) document.documentElement.scrollTop = 0;
    if (document.body) document.body.scrollTop = 0;
  }

  scrollToTop();
  document.addEventListener("DOMContentLoaded", scrollToTop, { once: true });
  window.addEventListener(
    "load",
    () => {
      scrollToTop();
      requestAnimationFrame(() => {
        scrollToTop();
        requestAnimationFrame(scrollToTop);
      });
      setTimeout(scrollToTop, 0);
      setTimeout(scrollToTop, 50);
      setTimeout(scrollToTop, 150);
      setTimeout(scrollToTop, 300);
    },
    { once: true },
  );
  window.addEventListener("pageshow", () => {
    scrollToTop();
    setTimeout(scrollToTop, 0);
  });
})();
