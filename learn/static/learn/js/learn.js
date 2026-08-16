/*
 * Fiscus Learn module.
 *
 * Both pages are protected: no Supabase session redirects to /?auth=1.
 * (?preview=1 bypasses the redirect for the static preview build.)
 *
 * lesson_list: fetch /api/lessons/attempts/ and show best-score
 * checkmarks + the current streak.
 *
 * lesson_detail: render the 3-question quiz, instant per-question feedback
 * (no reload), then record a QuizAttempt and toast any new badges.
 */
(function () {
  "use strict";

  var cfgEl = document.getElementById("fiscus-config");
  var cfg = cfgEl ? JSON.parse(cfgEl.textContent) : {};
  var client = window.supabase.createClient(cfg.supabase_url, cfg.supabase_anon_key);

  var previewMode = new URLSearchParams(window.location.search).has("preview");
  var progressEl = document.getElementById("lesson-progress");
  var quizRoot = document.getElementById("quiz-root");

  function redirectToLogin() {
    window.location.href = "/?auth=1";
  }

  function showToasts(items) {
    if (!items || !items.length) return;
    var wrap = document.getElementById("toast-wrap");
    if (!wrap) return;
    wrap.hidden = false;
    items.forEach(function (name) {
      var el = document.createElement("div");
      el.className = "toast toast--badge";
      el.textContent = "Badge unlocked: " + name;
      wrap.appendChild(el);
      setTimeout(function () {
        el.remove();
        if (!wrap.children.length) wrap.hidden = true;
      }, 5000);
    });
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  var logoutBtn = document.getElementById("logout-btn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", function () {
      client.auth.signOut().then(function () { window.location.href = "/"; });
    });
  }

  /* ---------------- lesson list: progress checkmarks ---------------- */
  function initList(session) {
    if (!session) return;
    var token = session.access_token;
    fetch("/api/lessons/attempts/", {
      headers: { Authorization: "Bearer " + token }
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var streakLabel = document.getElementById("streak-label");
        if (streakLabel && data.current_streak > 0) {
          streakLabel.textContent = "Current streak: " + data.current_streak + " day" + (data.current_streak === 1 ? "" : "s") + ".";
        }
        var best = {};
        (data.lessons || []).forEach(function (l) { best[l.slug] = l.best_score; });
        progressEl.querySelectorAll(".lesson-card").forEach(function (card) {
          var link = card.querySelector(".lesson-card__link");
          var slug = link.getAttribute("href").split("/").filter(Boolean).pop();
          var score = best[slug];
          if (score !== undefined) {
            var cta = card.querySelector(".lesson-card__cta");
            cta.textContent = score + "% ✓";
            cta.classList.add("lesson-card__cta--done");
          }
        });
      })
      .catch(function () { /* progress is a nicety; ignore failures */ });
  }

  /* ---------------- lesson detail: the quiz ---------------- */
  function initQuiz(session) {
    var quizData = JSON.parse(document.getElementById("quiz-data").textContent);
    var questions = quizData.questions || [];
    var lessonId = quizRoot.getAttribute("data-lesson-id");
    var answers = new Array(questions.length).fill(null);
    var answered = 0;
    var finished = false;

    function render() {
      var wrap = document.getElementById("quiz-questions");
      wrap.innerHTML = questions.map(function (q, qi) {
        var options = q.options.map(function (opt, oi) {
          return (
            '<button type="button" class="quiz__option" data-q="' + qi + '" data-o="' + oi + '">' +
              "<span class=\"quiz__key\">" + String.fromCharCode(65 + oi) + "</span>" +
              "<span>" + esc(opt) + "</span>" +
            "</button>"
          );
        }).join("");
        return (
          '<div class="quiz__question" data-q="' + qi + '">' +
            '<p class="quiz__q">' + (qi + 1) + ". " + esc(q.question) + "</p>" +
            '<div class="quiz__options">' + options + "</div>" +
          "</div>"
        );
      }).join("");
    }

    function lockQuestion(qi) {
      var questionEl = quizRoot.querySelector('.quiz__question[data-q="' + qi + '"]');
      var chosen = answers[qi];
      questionEl.querySelectorAll(".quiz__option").forEach(function (btn) {
        btn.disabled = true;
        var oi = Number(btn.getAttribute("data-o"));
        if (oi === questions[qi].correct) btn.classList.add("is-correct");
        else if (oi === chosen) btn.classList.add("is-wrong");
      });
    }

    function showResult(msg, isNotice) {
      var el = document.getElementById("quiz-result");
      el.textContent = msg;
      el.classList.toggle("quiz__result--notice", !!isNotice);
      el.hidden = false;
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    function maybeFinish() {
      if (finished || answered < questions.length) return;
      finished = true;
      var correct = questions.reduce(function (n, q, qi) {
        return n + (answers[qi] === q.correct ? 1 : 0);
      }, 0);
      var score = Math.round((correct / questions.length) * 100);

      if (!session) {
        showResult("Score: " + score + "% — log in to save your progress and build your streak.", true);
        return;
      }
      fetch("/api/lessons/" + lessonId + "/attempt/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + session.access_token
        },
        body: JSON.stringify({ answers: answers })
      })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res) {
          if (!res.ok) {
            showResult("Score: " + score + "% — couldn't save the attempt: " + (res.d.detail || "error"), true);
            return;
          }
          var streakMsg = res.d.streak > 1
            ? " — " + res.d.streak + "-day streak! Keep it going."
            : " — first day of a new streak. Come back tomorrow!";
          showResult("Score: " + res.d.score + "% (" + res.d.correct + "/" + res.d.total + " correct)" + streakMsg);
          if (res.d.unlocked_badges && res.d.unlocked_badges.length) {
            showToasts(res.d.unlocked_badges);
          }
        })
        .catch(function () {
          showResult("Score: " + score + "% — couldn't save the attempt (network error).", true);
        });
    }

    quizRoot.addEventListener("click", function (e) {
      var btn = e.target.closest(".quiz__option");
      if (!btn || btn.disabled) return;
      var qi = Number(btn.getAttribute("data-q"));
      var oi = Number(btn.getAttribute("data-o"));
      if (answers[qi] === null) {
        answers[qi] = oi;
        answered += 1;
        lockQuestion(qi); // instant feedback, question locks
        maybeFinish();
      }
    });

    render();
  }

  /* ---------------- boot ---------------- */
  client.auth.getSession().then(function (res) {
    var session = res.data && res.data.session ? res.data.session : null;
    if (!session && !previewMode) {
      redirectToLogin();
      return;
    }
    if (progressEl) initList(session);
    if (quizRoot) initQuiz(session);
  });
})();
