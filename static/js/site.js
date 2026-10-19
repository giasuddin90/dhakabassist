/* Progressive enhancement only.
 *
 * Every page works with JavaScript disabled: navigation is links, the quiz
 * and the accordions are forms and <details>. This file makes those smoother
 * and nothing more — no framework, no render-blocking work.
 */
(function () {
  "use strict";

  document.documentElement.classList.add("js");

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* -- Mobile navigation ------------------------------------------------ */

  var toggle = document.querySelector("[data-nav-toggle]");
  var nav = document.getElementById("primary-nav");
  if (toggle && nav) {
    toggle.addEventListener("click", function () {
      var open = nav.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(open));
    });
  }

  /* -- Accordions ------------------------------------------------------- */

  // Only one panel open at a time, matching the design.
  document.querySelectorAll("[data-accordion]").forEach(function (group) {
    group.addEventListener("toggle", function (event) {
      var item = event.target;
      if (item.tagName !== "DETAILS" || !item.open) return;
      group.querySelectorAll("details[open]").forEach(function (other) {
        if (other !== item) other.open = false;
      });
    });
  });

  /* -- Lesson tabs ------------------------------------------------------ */

  // Server-rendered panels; this swaps them without a round trip and keeps
  // the choice in the URL so a reload or a shared link lands on the same tab.
  var tablist = document.querySelector("[data-tabs]");
  if (tablist) {
    var tabs = Array.prototype.slice.call(tablist.querySelectorAll("[role=tab]"));

    var select = function (tab, pushState) {
      tabs.forEach(function (other) {
        var selected = other === tab;
        other.setAttribute("aria-selected", String(selected));
        other.tabIndex = selected ? 0 : -1;
        var panel = document.getElementById(other.getAttribute("aria-controls"));
        if (panel) panel.hidden = !selected;
      });
      if (pushState) {
        var url = new URL(window.location.href);
        url.searchParams.set("tab", tab.dataset.tab);
        history.replaceState(null, "", url);
      }
    };

    tablist.addEventListener("click", function (event) {
      var tab = event.target.closest("[role=tab]");
      if (!tab) return;
      event.preventDefault();
      select(tab, true);
    });

    tablist.addEventListener("keydown", function (event) {
      var step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
      if (!step) return;
      event.preventDefault();
      var index = tabs.indexOf(document.activeElement);
      var next = tabs[(index + step + tabs.length) % tabs.length];
      next.focus();
      select(next, true);
    });

    // Panels all render server-side so the content exists without JS; once
    // JS is running, collapse to the requested tab (or the first one).
    var wanted = new URL(window.location.href).searchParams.get("tab");
    var initial =
      (wanted && tablist.querySelector('[data-tab="' + CSS.escape(wanted) + '"]')) ||
      tablist.querySelector('[aria-selected="true"]') ||
      tabs[0];
    if (initial) select(initial, false);
  }

  /* -- Quiz ------------------------------------------------------------- */

  // Posts one answer and paints the result in place. The server stays the
  // only judge of correctness; the page never knows the answer in advance.
  var quiz = document.querySelector("[data-quiz]");
  if (quiz) {
    var feedback = quiz.querySelector("[data-quiz-feedback]");
    var nextForm = quiz.querySelector("[data-quiz-next]");
    // Wording comes from the page, so it is in the page's language.
    var text = quiz.dataset;

    quiz.addEventListener("submit", function (event) {
      var form = event.target.closest("[data-answer-form]");
      if (!form) return;
      event.preventDefault();

      var button = form.querySelector("button");
      if (button.disabled) return;
      button.disabled = true;

      fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { "X-Requested-With": "fetch" },
        credentials: "same-origin",
      })
        .then(function (response) {
          if (!response.ok) throw new Error("request failed");
          return response.json();
        })
        .then(function (data) {
          button.classList.add(data.correct ? "is-correct" : "is-wrong");
          var note = button.querySelector("[data-answer-note]");
          if (note) note.textContent = data.correct ? text.textCorrect : text.textTryAgain;
          if (data.correct) {
            quiz.querySelectorAll("[data-answer-form] button").forEach(function (other) {
              other.disabled = true;
            });
            if (feedback) {
              // The server sends the explanation already rendered and
              // sanitised, so library audio and diagrams appear here too.
              if (data.explanation) feedback.innerHTML = data.explanation;
              else feedback.textContent = text.textCorrectFull;
              feedback.className = "u-fs-16 quiz-feedback";
              feedback.style.color = "var(--ok)";
            }
            if (nextForm) nextForm.hidden = false;
          } else {
            if (feedback) {
              feedback.textContent = text.textNotQuite;
              feedback.style.color = "var(--err)";
            }
          }
        })
        .catch(function () {
          // Fall back to the plain form post, which always works.
          button.disabled = false;
          form.dataset.answerForm = "";
          form.removeAttribute("data-answer-form");
          form.submit();
        });
    });
  }

  /* -- Video position --------------------------------------------------- */

  // Saves where the student paused, so "Resume" is accurate, and how many
  // seconds were played since the last save, for staff to see study time.
  // Throttled to one write per 15 seconds, plus one on leaving the page.
  var video = document.querySelector("video[data-position-url]");
  if (video) {
    var lastSent = 0;
    var lastTime = video.currentTime || 0;
    var played = 0;
    var send = function (useBeacon) {
      var seconds = Math.floor(video.currentTime || 0);
      if (!seconds) return;
      var watched = Math.floor(played);
      played -= watched;
      var body = new FormData();
      body.append("seconds", String(seconds));
      body.append("watched", String(watched));
      body.append("csrfmiddlewaretoken", video.dataset.csrf);
      if (useBeacon && navigator.sendBeacon) {
        navigator.sendBeacon(video.dataset.positionUrl, body);
        return;
      }
      fetch(video.dataset.positionUrl, {
        method: "POST",
        body: body,
        credentials: "same-origin",
        keepalive: true,
      }).catch(function () {});
    };

    video.addEventListener("timeupdate", function () {
      // Small forward steps are playback; anything bigger is a seek.
      var step = video.currentTime - lastTime;
      lastTime = video.currentTime;
      if (step > 0 && step < 2) played += step / (video.playbackRate || 1);
      var now = Date.now();
      if (now - lastSent < 15000) return;
      lastSent = now;
      send(false);
    });
    video.addEventListener("pause", function () { send(false); });
    window.addEventListener("pagehide", function () { send(true); });

    var start = parseInt(video.dataset.startAt || "0", 10);
    if (start > 0) {
      video.addEventListener(
        "loadedmetadata",
        function () {
          if (start < video.duration - 5) video.currentTime = start;
        },
        { once: true }
      );
    }
  }

  /* -- Click-to-load media ---------------------------------------------- */

  // Posters stay lightweight until the student actually plays something.
  document.querySelectorAll("[data-load-media]").forEach(function (trigger) {
    trigger.addEventListener("click", function () {
      var target = document.getElementById(trigger.dataset.loadMedia);
      if (!target) return;
      target.hidden = false;
      trigger.hidden = true;
      var media = target.querySelector("video, audio, iframe");
      if (media && media.tagName !== "IFRAME") media.play().catch(function () {});
    });
  });

  /* -- Reveal on scroll ------------------------------------------------- */

  // `is-armed` is what hides an element, and it is added one element at a
  // time, immediately before observing it. A section can therefore never be
  // left hidden by a script that stopped early.
  var reveals = document.querySelectorAll(".reveal");
  if (reveals.length && !reduceMotion && "IntersectionObserver" in window) {
    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.05 }
    );
    reveals.forEach(function (el) {
      el.classList.add("is-armed");
      observer.observe(el);
    });
  }
})();
