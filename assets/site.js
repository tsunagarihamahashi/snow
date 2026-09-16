(function () {
  const R = window.RESORT;
  if (!R) return;
  const yen = (n) => "¥" + Number(n).toLocaleString();
  const $ = (id) => document.getElementById(id);

  let liftTotal = 0;
  let rentalTotal = 0;
  function updateGrandTotal() {
    const el = $("grandTotalAmount");
    if (el) el.textContent = yen(liftTotal + rentalTotal);
  }

  // ---------------------------------------------------------------- price
  function initPriceRows(P) {
    const catRows = $("catRows");
    if (!catRows) return;
    const counts = Object.assign({}, P.counts);
    let option = P.default_option;

    P.categories.forEach((cat) => {
      const row = document.createElement("div");
      row.className = "cat-row";
      row.innerHTML = `
        <div>
          <span class="cat-label">${cat.label}</span>
          ${cat.cond ? `<span class="cat-cond">${cat.cond}</span>` : ""}
        </div>
        <div class="cat-price" data-price="${cat.key}"></div>
        <div class="stepper">
          <button type="button" data-act="dec" data-key="${cat.key}" aria-label="${cat.label}を減らす">−</button>
          <input type="text" inputmode="numeric" readonly value="${counts[cat.key]}" data-count="${cat.key}">
          <button type="button" data-act="inc" data-key="${cat.key}" aria-label="${cat.label}を増やす">＋</button>
        </div>`;
      catRows.appendChild(row);
    });

    function prices() { return P.mode === "toggle" ? P.price_table[option] : P.prices; }
    function render() {
      const pr = prices();
      P.categories.forEach((cat) => {
        catRows.querySelector(`[data-price="${cat.key}"]`).textContent = yen(pr[cat.key]);
        catRows.querySelector(`[data-count="${cat.key}"]`).value = counts[cat.key];
      });
      const total = P.categories.reduce((s, cat) => s + pr[cat.key] * counts[cat.key], 0);
      $("totalAmount").textContent = yen(total);
      liftTotal = total;
      updateGrandTotal();
    }
    catRows.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-act]");
      if (!btn) return;
      const k = btn.dataset.key;
      counts[k] = btn.dataset.act === "inc" ? Math.min(counts[k] + 1, 20) : Math.max(counts[k] - 1, 0);
      render();
    });
    document.querySelectorAll(".daytype-toggle button").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".daytype-toggle button").forEach((b) => b.setAttribute("aria-pressed", "false"));
        btn.setAttribute("aria-pressed", "true");
        option = btn.dataset.day;
        render();
      });
    });
    render();
  }

  // 券種 x チャネル x 区分 の3軸 (line items)
  function initPriceLines(P) {
    const lineList = $("lineList");
    if (!lineList) return;
    const ticketTypes = P.ticket_types;
    const getTicket = (id) => ticketTypes.find((t) => t.id === id);
    const getCategory = (tid, key) => getTicket(tid).categories.find((c) => c.key === key);
    let seq = 0;
    const lines = [Object.assign({ id: seq++ }, P.default_line)];

    function priceOf(line) {
      const cat = getCategory(line.ticket, line.category);
      return cat.mode === "fixed" ? cat.price : cat.prices[line.channel];
    }
    function updateTotal() {
      const total = lines.reduce((s, l) => s + priceOf(l) * l.count, 0);
      $("totalAmount").textContent = yen(total);
      liftTotal = total;
      updateGrandTotal();
    }
    function render() {
      lineList.innerHTML = "";
      lines.forEach((line) => {
        const ticket = getTicket(line.ticket);
        if (!ticket.categories.find((c) => c.key === line.category)) line.category = ticket.categories[0].key;
        const cat = getCategory(line.ticket, line.category);
        const hasChannel = cat.mode === "channel";
        if (hasChannel && !ticket.channels.includes(line.channel)) line.channel = ticket.channels[0];
        const price = priceOf(line);
        const opt = (arr, val, lab) => arr.map((x) => `<option value="${x.v}" ${x.v === val ? "selected" : ""}>${x.l}</option>`).join("");
        const el = document.createElement("div");
        el.className = "line-item";
        el.innerHTML = `
          <div class="line-head">
            <div class="line-selects ${hasChannel ? "has-channel" : ""}">
              <select data-field="category" data-line="${line.id}">${opt(ticket.categories.map((c) => ({ v: c.key, l: c.label })), line.category)}</select>
              <select data-field="ticket" data-line="${line.id}">${opt(ticketTypes.map((t) => ({ v: t.id, l: t.label })), line.ticket)}</select>
              ${hasChannel ? `<select data-field="channel" data-line="${line.id}">${opt(ticket.channels.map((ch) => ({ v: ch, l: ticket.channelLabels[ch] })), line.channel)}</select>` : ""}
            </div>
            <button type="button" class="remove-line" data-remove="${line.id}" aria-label="この行を削除">×</button>
          </div>
          ${cat.cond ? `<p class="line-cond">${cat.cond}</p>` : ""}
          <div class="line-foot">
            <span class="line-price">${yen(price)} ${!hasChannel ? "（" + (cat.cond && cat.cond.includes("共通") ? "全チャネル共通" : "固定") + "）" : ""}</span>
            <div class="stepper">
              <button type="button" data-act="dec" data-line="${line.id}">−</button>
              <input type="text" readonly value="${line.count}" data-count-line="${line.id}">
              <button type="button" data-act="inc" data-line="${line.id}">＋</button>
            </div>
            <span class="line-subtotal">${yen(price * line.count)}</span>
          </div>`;
        lineList.appendChild(el);
      });
      updateTotal();
      const notes = [...new Set(lines.map((l) => getCategory(l.ticket, l.category).note).filter(Boolean))];
      $("calcFoot").textContent = notes.length ? notes.join(" / ") : P.empty_note;
    }
    lineList.addEventListener("click", (e) => {
      const step = e.target.closest("button[data-act]");
      if (step) {
        const line = lines.find((l) => l.id == step.dataset.line);
        line.count = step.dataset.act === "inc" ? Math.min(line.count + 1, 20) : Math.max(line.count - 1, 0);
        render();
        return;
      }
      const rm = e.target.closest("button[data-remove]");
      if (rm && lines.length > 1) {
        lines.splice(lines.findIndex((l) => l.id == rm.dataset.remove), 1);
        render();
      }
    });
    lineList.addEventListener("change", (e) => {
      const sel = e.target.closest("select[data-field]");
      if (!sel) return;
      lines.find((l) => l.id == sel.dataset.line)[sel.dataset.field] = sel.value;
      render();
    });
    $("addLineBtn").addEventListener("click", () => {
      lines.push(Object.assign({ id: seq++ }, P.add_line));
      render();
    });
    render();
  }

  // ---------------------------------------------------------------- rental
  function initRentalStepper(RT) {
    const rows = $("rentalCatRows");
    if (!rows) return;
    const counts = {};
    RT.items.forEach((it) => { counts[it.key] = 0; });
    RT.items.forEach((it) => {
      const row = document.createElement("div");
      row.className = "cat-row";
      row.innerHTML = `
        <div><span class="cat-label">${it.label}</span></div>
        <div class="cat-price">${yen(it.price)}</div>
        <div class="stepper">
          <button type="button" data-ract="dec" data-rkey="${it.key}" aria-label="${it.label}を減らす">−</button>
          <input type="text" inputmode="numeric" readonly value="0" data-rcount="${it.key}">
          <button type="button" data-ract="inc" data-rkey="${it.key}" aria-label="${it.label}を増やす">＋</button>
        </div>`;
      rows.appendChild(row);
    });
    const discountEl = $("rentalDiscount");
    function render() {
      let total = 0, n = 0;
      RT.items.forEach((it) => {
        rows.querySelector(`[data-rcount="${it.key}"]`).value = counts[it.key];
        total += it.price * counts[it.key];
        n += counts[it.key];
      });
      if (RT.discount && discountEl && discountEl.checked) total = Math.max(total - n * RT.discount.per_item, 0);
      $("rentalTotalAmount").textContent = yen(total);
      rentalTotal = total;
      updateGrandTotal();
    }
    rows.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-ract]");
      if (!btn) return;
      const k = btn.dataset.rkey;
      counts[k] = btn.dataset.ract === "inc" ? Math.min(counts[k] + 1, 20) : Math.max(counts[k] - 1, 0);
      render();
    });
    if (discountEl) discountEl.addEventListener("change", render);
    render();
  }

  function initRentalCart(RT) {
    const list = $("rentalLineList");
    if (!list) return;
    const plans = RT.plans;
    const getPlan = (id) => plans.find((p) => p.id === id);
    const getCat = (pid, key) => getPlan(pid).categories.find((c) => c.key === key);
    let seq = 0;
    const lines = [Object.assign({ id: seq++ }, RT.default_line)];
    function updateTotal() {
      const total = lines.reduce((s, l) => s + getCat(l.plan, l.category).price * l.count, 0);
      $("rentalTotalAmount").textContent = yen(total);
      rentalTotal = total;
      updateGrandTotal();
    }
    function render() {
      list.innerHTML = "";
      lines.forEach((line) => {
        const plan = getPlan(line.plan);
        if (!plan.categories.find((c) => c.key === line.category)) line.category = plan.categories[0].key;
        const cat = getCat(line.plan, line.category);
        const el = document.createElement("div");
        el.className = "line-item";
        el.innerHTML = `
          <div class="line-head">
            <div class="line-selects">
              <select data-rfield="plan" data-rline="${line.id}">${plans.map((p) => `<option value="${p.id}" ${p.id === line.plan ? "selected" : ""}>${p.label}</option>`).join("")}</select>
              <select data-rfield="category" data-rline="${line.id}">${plan.categories.map((c) => `<option value="${c.key}" ${c.key === line.category ? "selected" : ""}>${c.label}</option>`).join("")}</select>
            </div>
            <button type="button" class="remove-line" data-rremove="${line.id}" aria-label="この行を削除">×</button>
          </div>
          <div class="line-foot">
            <span class="line-price">${yen(cat.price)}</span>
            <div class="stepper">
              <button type="button" data-ract="dec" data-rline="${line.id}">−</button>
              <input type="text" readonly value="${line.count}" data-rcountline="${line.id}">
              <button type="button" data-ract="inc" data-rline="${line.id}">＋</button>
            </div>
            <span class="line-subtotal">${yen(cat.price * line.count)}</span>
          </div>`;
        list.appendChild(el);
      });
      updateTotal();
    }
    list.addEventListener("click", (e) => {
      const step = e.target.closest("button[data-ract]");
      if (step) {
        const line = lines.find((l) => l.id == step.dataset.rline);
        line.count = step.dataset.ract === "inc" ? Math.min(line.count + 1, 20) : Math.max(line.count - 1, 0);
        render();
        return;
      }
      const rm = e.target.closest("button[data-rremove]");
      if (rm && lines.length > 1) {
        lines.splice(lines.findIndex((l) => l.id == rm.dataset.rremove), 1);
        render();
      }
    });
    list.addEventListener("change", (e) => {
      const sel = e.target.closest("select[data-rfield]");
      if (!sel) return;
      lines.find((l) => l.id == sel.dataset.rline)[sel.dataset.rfield] = sel.value;
      render();
    });
    $("addRentalLineBtn").addEventListener("click", () => {
      lines.push(Object.assign({ id: seq++ }, RT.default_line, { count: 1 }));
      render();
    });
    render();
  }

  // ---------------------------------------------------------------- trail map modal
  function initMapModal() {
    const img = $("trailMapImg"), modal = $("mapModal"), modalImg = $("mapModalImg"), closeBtn = $("mapModalClose");
    if (!img || !modal) return;
    const open = () => { modalImg.src = img.src; modalImg.alt = img.alt; modal.classList.add("open"); document.body.style.overflow = "hidden"; };
    const close = () => { modal.classList.remove("open"); document.body.style.overflow = ""; };
    img.addEventListener("click", open);
    closeBtn.addEventListener("click", close);
    modal.addEventListener("click", (e) => { if (e.target === modal) close(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  }

  // ---------------------------------------------------------------- snow depth (snow_data.json, scraped daily)
  function initSnow(S) {
    const el = $("snowDepth");
    if (!el) return;
    fetch("snow_data.json").then((r) => r.json()).then((json) => {
      const d = json.resorts && json.resorts[S.key];
      if (!d || !d.available) {
        el.outerHTML = `<p class="snowdepth-unavailable">積雪の実測値は${(d && d.note) || "現在取得できません"}。<a href="${S.fallback_url}" target="_blank" rel="noopener">公式サイト</a>でご確認ください。</p>`;
        return;
      }
      const cells = S.layout === "top_mid_base"
        ? [["top", "上部 cm"], ["mid", "中間 cm"], ["base", "ベース cm"]]
        : [["amount", "積雪 cm"]];
      el.innerHTML = `
        <div class="sd-cells">${cells.map(([k, l]) => `<div class="sd-cell"><div class="sd-num">${d[k]}</div><div class="sd-label">${l}</div></div>`).join("")}</div>
        <div class="sd-updated">積雪実測値・公式サイト ${d.updated || ""} 更新</div>`;
    }).catch(() => { el.outerHTML = '<p class="snowdepth-unavailable">積雪データを取得できませんでした。</p>'; });
  }

  // ---------------------------------------------------------------- weather (Open-Meteo, no API key)
  function initWeather(W) {
    const row = $("weatherRow"), toggle = document.querySelector(".weather-toggle");
    if (!row || !toggle) return;
    const ICONS = {
      sun: '<svg class="w-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
      cloud: '<svg class="w-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 18a4 4 0 0 1-.6-7.96A5 5 0 0 1 15 8a3.5 3.5 0 0 1 3.4 4.24A3.5 3.5 0 0 1 17.5 18H6Z"/></svg>',
      rain: '<svg class="w-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 15a4 4 0 0 1-.6-7.96A5 5 0 0 1 15 5a3.5 3.5 0 0 1 3.4 4.24A3.5 3.5 0 0 1 17.5 15H6Z"/><path d="M8 18v2M12 18v2M16 18v2"/></svg>',
      snow: '<svg class="w-icon snow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 15a4 4 0 0 1-.6-7.96A5 5 0 0 1 15 5a3.5 3.5 0 0 1 3.4 4.24A3.5 3.5 0 0 1 17.5 15H6Z"/><circle cx="8" cy="19" r="0.9" fill="currentColor" stroke="none"/><circle cx="12" cy="20" r="0.9" fill="currentColor" stroke="none"/><circle cx="16" cy="19" r="0.9" fill="currentColor" stroke="none"/></svg>',
    };
    const wmo = (c) => {
      if ([71, 73, 75, 77, 85, 86].includes(c)) return "snow";
      if ([51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99].includes(c)) return "rain";
      if ([1, 2, 3, 45, 48].includes(c)) return "cloud";
      return "sun";
    };
    const url = `https://api.open-meteo.com/v1/forecast?latitude=${W.lat}&longitude=${W.lon}` +
      `&daily=weather_code,temperature_2m_max,temperature_2m_min,snowfall_sum` +
      `&hourly=temperature_2m,weather_code,snowfall&timezone=Asia%2FTokyo&forecast_days=7`;
    let data = null, range = "today";
    function renderCards() {
      if (!data) return;
      row.innerHTML = "";
      if (range === "today") {
        const today = data.hourly.time[0].slice(0, 10);
        data.hourly.time.forEach((t, i) => {
          if (t.slice(0, 10) !== today || Number(t.slice(11, 13)) % 3 !== 0) return;
          const snow = data.hourly.snowfall[i];
          row.innerHTML += `<div class="weather-card"><span class="w-time">${t.slice(11, 16)}</span>${ICONS[wmo(data.hourly.weather_code[i])]}<span class="w-temp">${Math.round(data.hourly.temperature_2m[i])}°</span>${snow > 0 ? `<span class="w-snow">雪 ${snow.toFixed(1)}cm</span>` : ""}</div>`;
        });
      } else {
        const n = range === "2day" ? 2 : 7;
        for (let i = 0; i < n; i++) {
          const date = new Date(data.daily.time[i] + "T00:00:00+09:00");
          const label = i === 0 ? "今日" : i === 1 ? "明日" : `${date.getMonth() + 1}/${date.getDate()}`;
          const snow = data.daily.snowfall_sum[i];
          row.innerHTML += `<div class="weather-card"><span class="w-time">${label}</span>${ICONS[wmo(data.daily.weather_code[i])]}<span class="w-temp">${Math.round(data.daily.temperature_2m_max[i])}°<span class="lo">/${Math.round(data.daily.temperature_2m_min[i])}°</span></span>${snow > 0 ? `<span class="w-snow">雪 ${snow.toFixed(0)}cm</span>` : ""}</div>`;
        }
      }
    }
    toggle.querySelectorAll("button").forEach((btn) => btn.addEventListener("click", () => {
      range = btn.dataset.range;
      toggle.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", "false"));
      btn.setAttribute("aria-pressed", "true");
      renderCards();
    }));
    fetch(url).then((r) => r.json()).then((json) => { data = json; renderCards(); })
      .catch(() => { row.innerHTML = '<p class="weather-foot">天気情報の取得に失敗しました。</p>'; });
  }

  // ---------------------------------------------------------------- season status
  function initSeason(S) {
    const start = new Date(S.start + "T00:00:00+09:00"), end = new Date(S.end + "T23:59:00+09:00"), now = new Date();
    const pill = $("statusPill"), st = $("statusText"), note = $("statusNote");
    if (!pill) return;
    const approx = S.approximate ? "（目安）" : "";
    if (now >= start && now <= end) {
      pill.classList.add("open");
      st.textContent = S.approximate ? "営業中（シーズン期間内・目安）" : "営業中（シーズン期間内）";
      note.textContent = "積雪・リフト稼働の最新状況は公式サイトでご確認ください";
    } else {
      pill.classList.add("closed");
      st.textContent = "営業期間外";
      note.textContent = now > end ? S.next_note : `オープンまで ${Math.ceil((start - now) / 86400000)} 日${approx}`;
    }
  }

  // ---------------------------------------------------------------- livecam
  function initLivecam(L) {
    if (!L || L.type === "linkout") return;
    const frame = $("lcFrame"), img = $("lcImg"), tabs = $("lcTabs"), label = $("lcLabel"), updated = $("lcUpdated");
    let current = L.cams[0];
    function srcOf(cam) {
      if (L.type === "youtube") return `https://www.youtube.com/embed/${cam.id}?autoplay=1&mute=1`;
      if (L.type === "skiday") return cam.src;
      return cam.url + "?t=" + Date.now();
    }
    function show() {
      if (frame) frame.src = srcOf(current);
      if (img) {
        img.src = srcOf(current);
        if (updated) updated.textContent = new Date().toLocaleTimeString("ja-JP", { hour: "2-digit", minute: "2-digit" }) + " 更新";
      }
      if (label) label.textContent = current.label;
    }
    if (tabs) {
      L.cams.forEach((cam, i) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = cam.label;
        btn.setAttribute("aria-pressed", i === 0 ? "true" : "false");
        btn.addEventListener("click", () => {
          current = cam;
          [...tabs.children].forEach((b) => b.setAttribute("aria-pressed", "false"));
          btn.setAttribute("aria-pressed", "true");
          show();
        });
        tabs.appendChild(btn);
      });
    }
    if (img) {
      show();
      setInterval(show, L.refresh_ms || 60000);
    }
    // iframes: initial src is rendered server-side; nothing to do until a tab is clicked
  }

  // ---------------------------------------------------------------- boot
  if (R.price.mode === "lines") initPriceLines(R.price); else initPriceRows(R.price);
  if (R.rental.mode === "stepper") initRentalStepper(R.rental);
  if (R.rental.mode === "cart") initRentalCart(R.rental);
  initMapModal();
  initSnow(R.snow);
  initWeather(R.weather);
  initSeason(R.season);
  initLivecam(R.livecam);
})();
