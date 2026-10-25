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

  /* -- Staff panel menu ------------------------------------------------- */

  var sideToggle = document.querySelector("[data-side-toggle]");
  var sideMenu = document.getElementById("manage-menu");
  if (sideToggle && sideMenu) {
    var setSide = function (open) {
      sideMenu.classList.toggle("is-open", open);
      sideToggle.setAttribute("aria-expanded", String(open));
    };
    sideToggle.addEventListener("click", function () {
      setSide(!sideMenu.classList.contains("is-open"));
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && sideMenu.classList.contains("is-open")) {
        setSide(false);
        sideToggle.focus();
      }
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

  /* -- Password checks -------------------------------------------------- */

  // Registration. Under "Password", the server's rules are listed up front;
  // each one gets a tick as soon as it is met, and a cross once the student
  // has left the field without meeting it (not mid-word). Under "Confirm
  // password", a line fills while the start matches, turns red once the two
  // differ, and goes green with a tick when they agree and the password
  // passes. The server repeats every check.
  var matchGroup = document.querySelector("[data-password-match]");
  if (matchGroup) {
    var passwords = matchGroup.querySelectorAll("input[type=password]");
    var matchStatus = matchGroup.querySelector("[data-password-match-status]");
    var matchText = matchGroup.querySelector("[data-password-match-text]");
    var checklist = matchGroup.querySelector("[data-password-checklist]");
    var signupForm = matchGroup.closest("form");

    if (passwords.length === 2 && matchStatus && matchText && checklist && signupForm) {
      var first = passwords[0];
      var second = passwords[1];
      var firstLabel = first.closest(".field");
      var secondLabel = second.closest(".field");
      var confirmBox = matchStatus.parentElement;
      var minLength = parseInt(first.getAttribute("minlength") || "0", 10);
      var wording = matchGroup.dataset;
      var touched = false;
      var edited = false;

      // Django's UserAttributeSimilarityValidator: it compares which
      // characters two strings share (SequenceMatcher.quick_ratio), not their
      // order, against the name, the email and each word in them.
      var tooSimilar = function (password) {
        var chars = Array.from(password.toLowerCase());
        return ["full_name", "email"].some(function (name) {
          var input = signupForm.elements[name];
          var value = input ? input.value.trim().toLowerCase() : "";
          if (!value) return false;
          return value.split(/[^\p{L}\p{N}_]+/u).concat(value).some(function (part) {
            var partChars = Array.from(part);
            if (chars.length >= 10 * partChars.length && partChars.length < 0.35 * chars.length) {
              return false;
            }
            var counts = {};
            partChars.forEach(function (ch) { counts[ch] = (counts[ch] || 0) + 1; });
            var shared = 0;
            chars.forEach(function (ch) {
              if (counts[ch]) {
                counts[ch] -= 1;
                shared += 1;
              }
            });
            return (2 * shared) / (chars.length + partChars.length) >= 0.7;
          });
        });
      };

      // The rules the browser can check. "Too common" needs the server's
      // list, so that item is only ever marked by a post.
      var check = function (password) {
        return {
          short: Array.from(password).length < minLength,
          numeric: /^\p{Nd}+$/u.test(password),
          similar: password !== "" && tooSimilar(password),
        };
      };

      var clearServerErrors = function (label) {
        label.classList.remove("field--invalid");
        label.querySelectorAll(".field__error").forEach(function (error) { error.remove(); });
      };

      var paint = function () {
        var a = first.value;
        var b = second.value;
        var rules = check(a);
        var passes = !rules.short && !rules.numeric && !rules.similar;
        var show = touched && a !== "";

        if (edited) firstLabel.classList.toggle("field--invalid", show && !passes);
        var met = {
          password_too_short: !rules.short,
          password_entirely_numeric: !rules.numeric,
          password_too_similar: !rules.similar,
        };
        checklist.querySelectorAll("[data-rule]").forEach(function (item) {
          var ok = met[item.dataset.rule];
          var isMet = a !== "" && ok === true;
          // A rule only the server checks keeps the last post's mark until
          // the password is changed.
          var isFailed = ok === undefined ? item.classList.contains("is-failed") && !edited
            : show && !ok;
          item.classList.toggle("is-met", isMet);
          item.classList.toggle("is-failed", isFailed);
          var status = item.querySelector("[data-rule-status]");
          var text = isMet ? wording.textMet : isFailed ? wording.textUnmet : "";
          if (status && status.textContent !== text) status.textContent = text;
        });

        var state = "";
        var fill = 0;
        if (b && a === b) {
          state = passes ? "match" : "fix";
          fill = 1;
        } else if (b && a.indexOf(b) === 0) {
          fill = b.length / a.length;
        } else if (b) {
          state = "mismatch";
          fill = 1;
        }
        confirmBox.classList.toggle("is-match", state === "match");
        confirmBox.classList.toggle("is-mismatch", state === "mismatch");
        matchStatus.style.setProperty("--pw-fill", String(fill));
        var message = {
          match: wording.textMatch,
          mismatch: wording.textMismatch,
          fix: wording.textFix,
        }[state] || "";
        if (matchText.textContent !== message) matchText.textContent = message;
      };

      first.addEventListener("input", function () {
        if (!edited) clearServerErrors(firstLabel);
        edited = true;
        paint();
      });
      first.addEventListener("blur", function () {
        touched = true;
        paint();
      });
      second.addEventListener("input", function () {
        clearServerErrors(secondLabel);
        touched = true;
        paint();
      });
      ["full_name", "email"].forEach(function (name) {
        var input = signupForm.elements[name];
        if (input) input.addEventListener("input", paint);
      });

      // Stop a post the server would only send back, which would also empty
      // both password fields. Similarity is left to the server to be safe.
      signupForm.addEventListener("submit", function (event) {
        var a = first.value;
        var rules = check(a);
        var badPassword = a !== "" && (rules.short || rules.numeric);
        var mismatch = second.value !== "" && a !== second.value;
        if (!badPassword && !mismatch) return;
        event.preventDefault();
        touched = true;
        edited = true;
        paint();
        (badPassword ? first : second).focus();
      });

      matchStatus.hidden = false;
      // Autofill or going back can leave values in both fields already.
      if (first.value) touched = true;
      paint();
    }
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
