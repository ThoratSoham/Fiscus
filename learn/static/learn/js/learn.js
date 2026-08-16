/*
 * Fiscus Learn module.
 *
 * lesson_list: if a Supabase session exists, fetch /api/lessons/attempts/
 * and show best-score checkmarks + the current streak.
 *
 * lesson_detail: render the 3-question quiz, give instant per-question
 * feedback (no reload), and record a QuizAttempt when all questions are
 * answered (requires a session; otherwise prompt login).
 */
(function () {
  "use strict";

  var cfgEl = document.getElementById("fiscus-config");
  var cfg = cfgEl ? JSON.parse(cfgEl.textContent) : {};
  var client = window.supabase.createClient(cfg.supabase_url, cfg.supabase_anon_key);

  /* ---------------- lesson list: progress checkmarks ---------------- */
  var progressEl = document.getElementById("lesson-progress");
  if (progressEl) {
    client.auth.getSession().then(function (res) {
      if (!res.data || !res.data.session) return;
      var token = res.data.session.access_token;
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
    });
    return; // list page: nothing else to do
  }

  /* ---------------- lesson detail: the quiz ---------------- */
  var quizRoot = document.getElementById("quiz-root");
  if (!quizRoot) return;

  var quizData = JSON.parse(document.getElementById("quiz-data").textContent);
  var questions = quizData.questions || [];
  var lessonId = quizRoot.getAttribute("data-lesson-id");
  var answers = new Array(questions.length).fill(null);
  var answered = 0;
  var finished = false;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

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

  function maybeFinish() {
    if (finished || answered < questions.length) return;
    finished = true;
    var correct = questions.reduce(function (n, q, qi) {
      return n + (answers[qi] === q.correct ? 1 : 0);
    }, 0);
    var score = Math.round((correct / questions.length) * 100);
    showResult("Score: " + score + "% (" + correct + "/" + questions.length + " correct)");

    client.auth.getSession().then(function (res) {
      if (!res.data || !res.data.session) {
        showResult("Score: " + score + "% — log in to save your progress and build your streak.", true);
        return;
      }
      fetch("/api/lessons/" + lessonId + "/attempt/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + res.data.session.access_token
        },
        body: JSON.stringify({ answers: answers })
      })
        .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
        .then(function (res2) {
          if (!res2.ok) {
            showResult("Saved the score, but streak update failed: " + (res2.d.detail || "error"), true);
            return;
          }
          var streakMsg = res2.d.streak > 1
            ? " — " + res2.d.streak + "-day streak! Keep it going."
            : " — first day of a new streak. Come back tomorrow!";
          showResult("Score: " + res2.d.score + "% (" + res2.d.correct + "/" + res2.d.total + " correct)" + streakMsg);
        })
        .catch(function () {
          showResult("Score: " + score + "% — couldn't save the attempt (network error).", true);
        });
    });
  }

  function showResult(msg, isNotice) {
    var el = document.getElementById("quiz-result");
    el.textContent = msg;
    el.classList.toggle("quiz__result--notice", !!isNotice);
    el.hidden = false;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
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
})();
