/*
 * Fiscus Invest (paper trading).
 *
 * Reads the Supabase session, calls the Django API with the access token,
 * and renders portfolio/holdings/prices. Every price comes from Fiscus's
 * own simulated market engine — deterministic per student, 24/7, no real
 * market data. A 5-second ticker re-queries the engine so prices feel
 * live without touching any external feed.
 */
(function () {
  "use strict";

  var cfgEl = document.getElementById("fiscus-config");
  var cfg = cfgEl ? JSON.parse(cfgEl.textContent) : {};
  var client = window.supabase.createClient(cfg.supabase_url, cfg.supabase_anon_key);

  /* Preview mode: the standalone preview.html has no session or Django API.
     It injects mock data and skips the login redirect so the UI can be
     visually QA'd. Never set in production. */
  var PREVIEW = !!window.FISCUS_PREVIEW;

  var state = { token: null, instruments: [], portfolio: null };

  var PALETTE = {
    blue: "#0038ff",
    red: "#e00000",
    green: "#0a7d2c",
    black: "#0b0b0d",
    grey: "#c9c9d2"
  };

  function money(n) {
    return "₹" + Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function signedMoney(n) {
    var v = Number(n);
    return (v >= 0 ? "+" : "−") + money(Math.abs(v));
  }

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function redirectToLogin() {
    window.location.href = "/?auth=1";
  }

  /* ---- API (same contract as the other dashboards) ---- */
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
      var refreshed = await client.auth.refreshSession().then(function (r) {
        if (r.data && r.data.session) {
          state.token = r.data.session.access_token;
          return true;
        }
        return false;
      }).catch(function () { return false; });
      if (refreshed && !opts._retried) {
        opts._retried = true;
        return api(path, opts);
      }
      redirectToLogin();
      throw new Error("unauthorized");
    }
    var text = await res.text();
    var data = null;
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

  /* ---- load + render ---- */
  async function loadAll() {
    if (PREVIEW) {
      state.instruments = window.FISCUS_MOCK.instruments || [];
      state.portfolio = window.FISCUS_MOCK.portfolio || null;
      render();
      return;
    }
    var instrumentsRes = await api("/api/invest/instruments/");
    var portfolio = await api("/api/invest/portfolio/");
    state.instruments = instrumentsRes.instruments || [];
    state.portfolio = portfolio;
    render();
  }

  /* Ticker: refresh prices + portfolio every 5s without resetting the order
     form's selected instrument/quantity. */
  async function tick() {
    if (PREVIEW) return;
    try {
      var instrumentsRes = await api("/api/invest/instruments/");
      var portfolio = await api("/api/invest/portfolio/");
      var prevSel = document.getElementById("order-instrument").value;
      var prevQty = document.getElementById("order-quantity").value;
      state.instruments = instrumentsRes.instruments || [];
      state.portfolio = portfolio;
      render();
      document.getElementById("order-instrument").value = prevSel;
      document.getElementById("order-quantity").value = prevQty;
      updateOrderHint();
    } catch (err) {
      /* transient — keep the page on screen */
    }
  }

  function render() {
    renderMarketStatus();
    renderSelect();
    renderSummary();
    renderHoldings();
    renderInstruments();
    renderOrders();
  }

  function renderMarketStatus() {
    var dot = document.getElementById("market-dot");
    var label = document.getElementById("market-status");
    dot.className = "market-dot market-dot--open";
    label.textContent =
      "Simulated market — open 24/7. Prices are generated by Fiscus's own engine, " +
      "private to your portfolio. No real money, no real market data.";
  }

  function renderSelect() {
    var prev = document.getElementById("order-instrument").value;
    document.getElementById("order-instrument").innerHTML = state.instruments
      .map(function (i) {
        return '<option value="' + i.id + '" data-price="' + esc(i.price) + '">' +
          esc(i.symbol) + " — " + esc(i.name) + " (" + money(i.price) + ")" +
          "</option>";
      })
      .join("");
    if (prev) document.getElementById("order-instrument").value = prev;
    updateOrderHint();
  }

  function updateOrderHint() {
    var el = document.getElementById("order-hint");
    var select = document.getElementById("order-instrument");
    var side = document.getElementById("order-side").value;
    var qty = document.getElementById("order-quantity").value;
    var opt = select.selectedOptions[0];
    if (!opt || !qty) { el.textContent = ""; return; }
    var price = Number(opt.getAttribute("data-price"));
    var total = price * Number(qty);
    el.textContent = "This order " + (side === "buy" ? "will cost" : "will credit") +
      " approximately " + money(total) + " at the current simulated price.";
  }

  function renderSummary() {
    var p = state.portfolio;
    if (!p) return;
    document.getElementById("chip-value").textContent = money(p.portfolio_value);
    document.getElementById("chip-cash").textContent = money(p.cash);
    document.getElementById("chip-invested").textContent = money(p.invested);
    var ret = document.getElementById("chip-return");
    ret.textContent = signedMoney(p.return_amount) + " (" + signedMoney(p.return_pct) + "%)";
    ret.style.color = Number(p.return_amount) < 0 ? PALETTE.red : (Number(p.return_amount) > 0 ? PALETTE.green : "inherit");
  }

  function renderHoldings() {
    var wrap = document.getElementById("holdings-list");
    var p = state.portfolio;
    if (!p || !p.holdings.length) {
      wrap.innerHTML = '<p class="empty">No open positions. Place your first trade above — it unlocks the First Trade badge.</p>';
      return;
    }
    wrap.innerHTML =
      '<table class="inv-table">' +
        "<thead><tr><th>Instrument</th><th class=\"num\">Qty</th><th class=\"num\">Avg price</th>" +
        "<th class=\"num\">Last</th><th class=\"num\">Invested</th><th class=\"num\">Value</th>" +
        "<th class=\"num\">P&amp;L</th></tr></thead><tbody>" +
        p.holdings.map(function (h) {
          var pnl = Number(h.pnl);
          var pnlColor = pnl < 0 ? PALETTE.red : (pnl > 0 ? PALETTE.green : "inherit");
          return (
            "<tr>" +
              "<td><strong>" + esc(h.symbol) + "</strong><br><span class=\"muted\">" + esc(h.name) + "</span></td>" +
              '<td class="num">' + Number(h.quantity) + "</td>" +
              '<td class="num">' + money(h.avg_price) + "</td>" +
              '<td class="num">' + money(h.last_price) + "</td>" +
              '<td class="num">' + money(h.invested) + "</td>" +
              '<td class="num">' + money(h.current_value) + "</td>" +
              '<td class="num" style="color:' + pnlColor + '">' + signedMoney(h.pnl) + " (" + signedMoney(h.pnl_pct) + "%)</td>" +
            "</tr>"
          );
        }).join("") +
        "</tbody></table>";
  }

  function renderInstruments() {
    var wrap = document.getElementById("instruments-list");
    wrap.innerHTML =
      '<table class="inv-table">' +
        "<thead><tr><th>Symbol</th><th>Name</th><th>Kind</th><th class=\"num\">Last price</th>" +
        "<th>As of</th><th>Status</th></tr></thead><tbody>" +
        state.instruments.map(function (i) {
          var asOf = i.as_of ? new Date(i.as_of).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" }) : "—";
          return (
            "<tr>" +
              "<td><strong>" + esc(i.symbol) + "</strong></td>" +
              "<td>" + esc(i.name) + "</td>" +
              "<td>" + esc(i.kind) + "</td>" +
              '<td class="num">' + money(i.price) + "</td>" +
              "<td>" + asOf + "</td>" +
              '<td><span class="ok">simulated</span></td>' +
            "</tr>"
          );
        }).join("") +
        "</tbody></table>";
  }

  function renderOrders() {
    var wrap = document.getElementById("orders-list");
    var p = state.portfolio;
    if (!p || !p.recent_orders.length) {
      wrap.innerHTML = '<p class="empty">No orders yet.</p>';
      return;
    }
    wrap.innerHTML =
      '<table class="inv-table">' +
        "<thead><tr><th>When</th><th>Side</th><th>Instrument</th><th class=\"num\">Qty</th>" +
        "<th class=\"num\">Price</th><th class=\"num\">Total</th></tr></thead><tbody>" +
        p.recent_orders.map(function (o) {
          var color = o.side === "buy" ? PALETTE.blue : PALETTE.red;
          return (
            "<tr>" +
              "<td>" + new Date(o.created_at).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" }) + "</td>" +
              '<td style="color:' + color + '"><strong>' + esc(o.side.toUpperCase()) + "</strong></td>" +
              "<td>" + esc(o.instrument_symbol) + "</td>" +
              '<td class="num">' + Number(o.quantity) + "</td>" +
              '<td class="num">' + money(o.price) + "</td>" +
              '<td class="num">' + money(o.price * Number(o.quantity)) + "</td>" +
            "</tr>"
          );
        }).join("") +
        "</tbody></table>";
  }

  /* ---- actions ---- */
  async function submitOrder(event) {
    event.preventDefault();
    if (PREVIEW) {
      alert("Trading is disabled in this static preview — place orders on the deployed site.");
      return;
    }
    var instrumentId = document.getElementById("order-instrument").value;
    var side = document.getElementById("order-side").value;
    var quantity = document.getElementById("order-quantity").value;
    var note = document.getElementById("order-note").value.trim();
    if (!instrumentId || !quantity) return;
    var btn = document.getElementById("order-submit");
    btn.disabled = true;
    btn.textContent = "Placing…";
    try {
      var res = await api("/api/invest/orders/", {
        method: "POST",
        body: JSON.stringify({ instrument_id: instrumentId, side: side, quantity: quantity, note: note })
      });
      showToasts(res.unlocked_badges);
      document.getElementById("order-quantity").value = "";
      document.getElementById("order-note").value = "";
      await loadAll();
    } catch (err) {
      alert(err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = "Place order";
    }
  }

  async function resetPortfolio() {
    if (PREVIEW) {
      alert("Reset is disabled in this static preview.");
      return;
    }
    if (!window.confirm("Reset your portfolio? This wipes all holdings and orders, restores your starting balance, and re-rolls your private market.")) return;
    try {
      await api("/api/invest/reset/", { method: "POST" });
      await loadAll();
    } catch (err) {
      alert(err.message);
    }
  }

  function bind() {
    document.getElementById("order-form").addEventListener("submit", submitOrder);
    document.getElementById("reset-btn").addEventListener("click", resetPortfolio);
    document.getElementById("order-side").addEventListener("change", updateOrderHint);
    document.getElementById("order-quantity").addEventListener("input", updateOrderHint);
    document.getElementById("logout-btn").addEventListener("click", function () {
      client.auth.signOut().then(function () { window.location.href = "/"; });
    });
  }

  /* ---- boot ---- */
  function boot(session) {
    if (session) state.token = session.access_token;
    bind();
    if (PREVIEW) document.getElementById("logout-btn").hidden = true;
    loadAll().then(function () {
      if (!PREVIEW) setInterval(tick, 5000);
    }).catch(function (err) {
      if (err && err.message !== "unauthorized") alert(err.message);
    });
  }

  if (PREVIEW) {
    boot(null);
  } else {
    client.auth.getSession().then(function (res) {
      if (!res.data || !res.data.session) {
        redirectToLogin();
        return;
      }
      boot(res.data.session);
    });
  }
})();
