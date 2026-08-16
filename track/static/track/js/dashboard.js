/*
 * Fiscus Track dashboard.
 *
 * Reads the Supabase session from supabase-js, calls the Django API with
 * `Authorization: Bearer <access_token>`, and renders budget progress bars,
 * Chart.js charts, and the expense list. Every mutation re-fetches and
 * re-renders so bars react live.
 */
(function () {
  "use strict";

  var cfgEl = document.getElementById("fiscus-config");
  var cfg = cfgEl ? JSON.parse(cfgEl.textContent) : {};
  var client = window.supabase.createClient(cfg.supabase_url, cfg.supabase_anon_key);

  var state = { token: null, expenses: [], budgets: [], categories: [], dashboard: null };
  var editingId = null;
  var charts = { pie: null, bar: null };

  var PALETTE = {
    blue: "#0038ff",
    blueDeep: "#0023a8",
    black: "#0b0b0d",
    white: "#ffffff",
    red: "#e00000",
    grey: "#c9c9d2"
  };

  function money(n) {
    return "₹" + Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function redirectToLogin() {
    window.location.href = "/?auth=1";
  }

  /* ---- API ---- */
  async function api(path, opts) {
    opts = opts || {};
    var headers = { "Content-Type": "application/json" };
    if (state.token) headers["Authorization"] = "Bearer " + state.token;
    var res = await fetch(path, {
      method: opts.method || "GET",
      headers: headers,
      body: opts.body || undefined
    });
    if (res.status === 401) {
      redirectToLogin();
      throw new Error("unauthorized");
    }
    var data = null;
    var text = await res.text();
    if (text) {
      try { data = JSON.parse(text); } catch (e) { data = null; }
    }
    if (!res.ok) {
      var msg = "Request failed (" + res.status + ")";
      if (data && data.detail) msg = data.detail;
      else if (data && typeof data === "object") {
        var first = Object.keys(data)[0];
        if (first && data[first]) msg = first + ": " + String(data[first]);
      }
      throw new Error(msg);
    }
    return data;
  }

  /* ---- load + render ---- */
  async function loadAll() {
    var results = await Promise.all([
      api("/api/dashboard/"),
      api("/api/expenses/"),
      api("/api/budgets/"),
      api("/api/categories/")
    ]);
    state.dashboard = results[0];
    state.expenses = results[1];
    state.budgets = results[2];
    state.categories = results[3];
    render();
  }

  function render() {
    renderSummary();
    renderBudgets();
    renderCharts();
    renderExpenses();
    renderSelects();
  }

  function renderSummary() {
    document.getElementById("month-label").textContent = state.dashboard.month;
    document.getElementById("chip-spent").textContent = money(state.dashboard.spent_total);
    document.getElementById("chip-income").textContent = money(state.dashboard.income_total);
    var netEl = document.getElementById("chip-net");
    netEl.textContent = money(state.dashboard.net);
    netEl.style.color = state.dashboard.net < 0 ? PALETTE.red : "inherit";
  }

  function renderBudgets() {
    var wrap = document.getElementById("budget-list");
    if (!state.budgets.length) {
      wrap.innerHTML = '<p class="empty">No budgets yet — set one below.</p>';
      return;
    }
    wrap.innerHTML = state.budgets.map(function (b) {
      var pct = Math.min(b.percent, 100);
      var cls = b.over ? "bar__fill bar__fill--over" : "bar__fill";
      return (
        '<div class="budget-row">' +
          '<div class="budget-row__head">' +
            '<span class="budget-row__name">' + esc(b.category) + "</span>" +
            '<span class="budget-row__nums">' + money(b.spent) + " of " + money(b.limit) + "</span>" +
          "</div>" +
          '<div class="bar"><div class="' + cls + '" style="width:' + pct + '%"></div></div>' +
          (b.over
            ? '<p class="budget-row__alert">Over budget by ' + money(b.spent - b.limit) + "</p>"
            : "") +
        "</div>"
      );
    }).join("");
  }

  function renderCharts() {
    if (!window.Chart) return;
    if (charts.pie) charts.pie.destroy();
    if (charts.bar) charts.bar.destroy();

    var byCat = state.dashboard.spent_by_category || [];
    var colors = byCat.map(function (_, i) {
      return i % 2 === 0 ? PALETTE.blue : (i % 4 === 1 ? PALETTE.black : PALETTE.blueDeep);
    });

    charts.pie = new Chart(document.getElementById("pie-chart"), {
      type: "pie",
      data: {
        labels: byCat.map(function (c) { return c.name; }),
        datasets: [{ data: byCat.map(function (c) { return c.total; }), backgroundColor: colors, borderColor: PALETTE.black, borderWidth: 2 }]
      },
      options: { plugins: { legend: { labels: { color: PALETTE.black, font: { family: "ui-monospace, monospace" } } } }, responsive: true }
    });

    charts.bar = new Chart(document.getElementById("bar-chart"), {
      type: "bar",
      data: {
        labels: state.dashboard.trend.map(function (t) { return t.label; }),
        datasets: [{
          label: "Spend",
          data: state.dashboard.trend.map(function (t) { return t.total; }),
          backgroundColor: PALETTE.blue,
          borderColor: PALETTE.black,
          borderWidth: 2
        }]
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: PALETTE.black, font: { family: "ui-monospace, monospace" } }, grid: { color: PALETTE.grey } },
          y: { ticks: { color: PALETTE.black, font: { family: "ui-monospace, monospace" } }, grid: { color: PALETTE.grey } }
        }
      }
    });
  }

  function renderExpenses() {
    var wrap = document.getElementById("expense-list");
    if (!state.expenses.length) {
      wrap.innerHTML = '<p class="empty">Nothing here yet — add your first entry above.</p>';
      return;
    }
    wrap.innerHTML =
      '<table class="expense-table">' +
        "<thead><tr><th>Date</th><th>Type</th><th>Category</th><th>Note</th><th class=\"num\">Amount</th><th></th></tr></thead>" +
        "<tbody>" +
        state.expenses.map(function (e) {
          var sign = e.type === "income" ? "+" : "−";
          var typeCls = e.type === "income" ? "badge badge--income" : "badge badge--expense";
          return (
            "<tr>" +
              "<td>" + esc(e.date) + "</td>" +
              '<td><span class="' + typeCls + '">' + (e.type === "income" ? "IN" : "OUT") + "</span></td>" +
              "<td>" + esc(e.category_name || "—") + "</td>" +
              "<td>" + esc(e.note || "") + "</td>" +
              '<td class="num">' + sign + money(e.amount) + "</td>" +
              '<td class="row-actions">' +
                '<button class="btn btn--sm" data-edit="' + e.id + '">Edit</button> ' +
                '<button class="btn btn--sm" data-delete="' + e.id + '">Delete</button>' +
              "</td>" +
            "</tr>"
          );
        }).join("") +
        "</tbody></table>";
  }

  function renderSelects() {
    var expenseCat = document.getElementById("expense-category");
    var budgetCat = document.getElementById("budget-category");
    var expenseOptions = state.categories
      .filter(function (c) { return c.kind === "expense" || c.kind === "both"; })
      .map(function (c) { return '<option value="' + c.id + '">' + esc(c.name) + "</option>"; })
      .join("");
    var incomeOptions = state.categories
      .filter(function (c) { return c.kind === "income" || c.kind === "both"; })
      .map(function (c) { return '<option value="' + c.id + '">' + esc(c.name) + "</option>"; })
      .join("");
    expenseCat.innerHTML = expenseOptions || '<option value="">—</option>';
    budgetCat.innerHTML = expenseOptions;

    /* category select follows the type toggle */
    document.getElementById("expense-type").addEventListener("change", function (e) {
      expenseCat.innerHTML = e.target.value === "income" ? incomeOptions : expenseOptions;
    });
  }

  /* ---- expense form ---- */
  function fillExpenseForm(e) {
    editingId = e.id;
    document.getElementById("expense-type").value = e.type;
    document.getElementById("expense-amount").value = e.amount;
    document.getElementById("expense-category").value = e.category || "";
    document.getElementById("expense-date").value = e.date;
    document.getElementById("expense-note").value = e.note || "";
    document.getElementById("expense-panel-title").textContent = "Edit entry";
    document.getElementById("expense-submit").textContent = "Save";
    document.getElementById("expense-cancel").hidden = false;
    document.getElementById("expense-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function resetExpenseForm() {
    editingId = null;
    document.getElementById("expense-form").reset();
    document.getElementById("expense-date").value = new Date().toISOString().slice(0, 10);
    document.getElementById("expense-panel-title").textContent = "Add entry";
    document.getElementById("expense-submit").textContent = "Add";
    document.getElementById("expense-cancel").hidden = true;
  }

  async function submitExpense(event) {
    event.preventDefault();
    var payload = {
      type: document.getElementById("expense-type").value,
      amount: document.getElementById("expense-amount").value,
      category: document.getElementById("expense-category").value || null,
      date: document.getElementById("expense-date").value,
      note: document.getElementById("expense-note").value.trim()
    };
    try {
      if (editingId) {
        await api("/api/expenses/" + editingId + "/", { method: "PATCH", body: JSON.stringify(payload) });
      } else {
        await api("/api/expenses/", { method: "POST", body: JSON.stringify(payload) });
      }
      resetExpenseForm();
      await loadAll();
    } catch (err) {
      alert(err.message);
    }
  }

  async function deleteExpense(id) {
    if (!window.confirm("Delete this entry?")) return;
    try {
      await api("/api/expenses/" + id + "/", { method: "DELETE" });
      await loadAll();
    } catch (err) {
      alert(err.message);
    }
  }

  /* ---- budget form ---- */
  async function submitBudget(event) {
    event.preventDefault();
    var categoryId = document.getElementById("budget-category").value;
    var limit = document.getElementById("budget-limit").value;
    if (!categoryId || !limit) return;
    try {
      var existing = state.budgets.find(function (b) { return String(b.category_id) === String(categoryId); });
      if (existing) {
        await api("/api/budgets/" + existing.id + "/", { method: "PATCH", body: JSON.stringify({ monthly_limit: limit }) });
      } else {
        await api("/api/budgets/", { method: "POST", body: JSON.stringify({ category: categoryId, monthly_limit: limit }) });
      }
      document.getElementById("budget-limit").value = "";
      await loadAll();
    } catch (err) {
      alert(err.message);
    }
  }

  /* ---- events ---- */
  function bind() {
    document.getElementById("expense-form").addEventListener("submit", submitExpense);
    document.getElementById("expense-cancel").addEventListener("click", resetExpenseForm);
    document.getElementById("budget-form").addEventListener("submit", submitBudget);
    document.getElementById("logout-btn").addEventListener("click", function () {
      client.auth.signOut().then(function () { window.location.href = "/"; });
    });

    document.getElementById("expense-list").addEventListener("click", function (e) {
      var del = e.target.closest("[data-delete]");
      var edit = e.target.closest("[data-edit]");
      if (del) deleteExpense(del.getAttribute("data-delete"));
      else if (edit) {
        var found = state.expenses.find(function (x) { return String(x.id) === String(edit.getAttribute("data-edit")); });
        if (found) fillExpenseForm(found);
      }
    });
  }

  /* ---- boot ---- */
  client.auth.getSession().then(function (res) {
    if (!res.data || !res.data.session) {
      redirectToLogin();
      return;
    }
    state.token = res.data.session.access_token;
    bind();
    document.getElementById("expense-date").value = new Date().toISOString().slice(0, 10);
    loadAll().catch(function (err) {
      if (err && err.message !== "unauthorized") alert(err.message);
    });
  });
})();
