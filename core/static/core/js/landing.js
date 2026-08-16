/* Fiscus landing page — Supabase auth wiring (email/password + magic link). */
(function () {
  "use strict";

  var cfgEl = document.getElementById("fiscus-config");
  var cfg = cfgEl ? JSON.parse(cfgEl.textContent) : {};
  var supabaseUrl = cfg.supabase_url || "";
  var supabaseAnonKey = cfg.supabase_anon_key || "";

  function isPlaceholder(v) {
    return (
      !v ||
      v.indexOf("your-anon-key") !== -1 ||
      v.indexOf("<project-ref>") !== -1 ||
      v.indexOf("example.com") !== -1
    );
  }

  var configured = !isPlaceholder(supabaseUrl) && !isPlaceholder(supabaseAnonKey);
  var client = null;

  if (configured && window.supabase) {
    client = window.supabase.createClient(supabaseUrl, supabaseAnonKey);
  } else if (!configured) {
    console.warn("Fiscus: Supabase keys look like placeholders — auth disabled.");
  }

  var form = document.getElementById("auth-form");
  var emailInput = document.getElementById("auth-email");
  var passwordInput = document.getElementById("auth-password");
  var statusEl = document.getElementById("auth-status");
  var logoutBtn = document.getElementById("auth-logout");
  var dashboardLink = document.getElementById("auth-dashboard");

  function setStatus(msg, tone) {
    statusEl.textContent = msg || "";
    if (tone) statusEl.setAttribute("data-tone", tone);
    else statusEl.removeAttribute("data-tone");
    statusEl.hidden = !msg;
  }

  function email() {
    return emailInput.value.trim();
  }

  function password() {
    return passwordInput.value;
  }

  function handleUser(user) {
    if (user) {
      setStatus("Logged in as " + user.email, "ok");
      logoutBtn.hidden = false;
      if (dashboardLink) dashboardLink.hidden = false;
    } else {
      setStatus("", "");
      logoutBtn.hidden = true;
      if (dashboardLink) dashboardLink.hidden = true;
    }
  }

  /* Reflect current/initial auth state. */
  if (client) {
    client.auth.onAuthStateChange(function (event, session) {
      if (event === "SIGNED_IN" && session) handleUser(session.user);
      if (event === "SIGNED_OUT") handleUser(null);
    });
    client.auth.getSession().then(function (res) {
      if (res && res.data && res.data.session) handleUser(res.data.session.user);
    });
  }

  logoutBtn.addEventListener("click", function () {
    if (!client) return;
    client.auth.signOut().then(function (res) {
      if (res.error) setStatus(res.error.message, "error");
      else handleUser(null);
    });
  });

  /* Google OAuth — Supabase redirects back to the Site URL with a session */
  var googleBtn = document.getElementById("auth-google");
  if (googleBtn) {
    googleBtn.addEventListener("click", function () {
      if (!client) {
        setStatus(
          "Supabase isn't configured yet — add your keys to .env (or the Vercel env vars) and redeploy.",
          "error"
        );
        return;
      }
      client.auth.signInWithOAuth({ provider: "google" }).then(function (res) {
        if (res.error) setStatus(res.error.message, "error");
      });
    });
  }

  /* Deep link from the dashboard: scroll straight to the auth form. */
  if (new URLSearchParams(window.location.search).has("auth")) {
    var target = document.getElementById("auth");
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();

    if (!client) {
      setStatus(
        "Supabase isn't configured yet — add your keys to .env (or the Vercel env vars) and redeploy.",
        "error"
      );
      return;
    }

    var action = e.submitter ? e.submitter.getAttribute("data-action") : "signup";

    if (!email()) {
      setStatus("Enter your email first.", "error");
      return;
    }

    setStatus("Working…", "");

    if (action === "signup") {
      if (password().length < 6) {
        setStatus("Password must be at least 6 characters.", "error");
        return;
      }
      client.auth.signUp({ email: email(), password: password() }).then(function (res) {
        if (res.error) {
          setStatus(res.error.message, "error");
          return;
        }
        /* With email confirmation enabled, session is null until verified. */
        if (res.data.session) handleUser(res.data.session.user);
        else setStatus("Account created — check your email to confirm, then log in.", "ok");
      });
    } else if (action === "login") {
      if (!password()) {
        setStatus("Enter your password.", "error");
        return;
      }
      client.auth.signInWithPassword({ email: email(), password: password() }).then(function (res) {
        if (res.error) setStatus(res.error.message, "error");
        else if (res.data.session) handleUser(res.data.session.user);
      });
    } else if (action === "magic") {
      client.auth.signInWithOtp({ email: email() }).then(function (res) {
        if (res.error) setStatus(res.error.message, "error");
        else setStatus("Magic link sent — check your inbox.", "ok");
      });
    }
  });
})();
