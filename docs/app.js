(function () {
  "use strict";

  const D = window.DASHBOARD_DATA;
  const $ = (s) => document.querySelector(s);
  const yen = (v) => (v == null ? "–" : "¥" + Math.round(v).toLocaleString("ja-JP"));
  const num = (v, d = 0) => (v == null ? "–" : Number(v).toLocaleString("ja-JP", { minimumFractionDigits: d, maximumFractionDigits: d }));
  const pctTxt = (v) => (v == null ? "–" : (v > 0 ? "+" : "") + (v * 100).toFixed(1) + "%");
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const round10 = (v) => Math.round(v / 10) * 10;
  const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();

  function quantile(values, q) {
    if (!values.length) return null;
    const s = [...values].sort((a, b) => a - b);
    const k = (s.length - 1) * q;
    const lo = Math.floor(k), hi = Math.min(lo + 1, s.length - 1);
    return s[lo] + (s[hi] - s[lo]) * (k - lo);
  }
  const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
  const addDays = (iso, n) => {
    const d = new Date(iso + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + n);
    return d.toISOString().slice(0, 10);
  };

  const state = { sort: { k: "rank", asc: true }, selected: null };
  const charts = {};

  // ---------- 初期化 ----------
  $("#meta").textContent = `データ日付 ${D.latest_date}（日次更新）・生成 ${D.generated_at.replace("T", " ")}`;
  $("#demo-banner").hidden = !D.is_demo;
  $("#m-rate").textContent = `${Math.round(D.config.review_rate * 100)}%`;

  const uniq = (k) => [...new Set(D.products.map((p) => p[k]).filter(Boolean))].sort((a, b) => a.localeCompare(b, "ja"));
  for (const [sel, key] of [["#f-variety", "variety"], ["#f-pref", "prefecture"]]) {
    for (const v of uniq(key)) $(sel).insertAdjacentHTML("beforeend", `<option>${esc(v)}</option>`);
  }
  for (const p of D.products) {
    p.pchg = p.price && p.price_7d ? (p.price - p.price_7d) / p.price_7d : null;
    p.status = p.active ? (p.sold_out ? 1 : 0) : 2;
    p.byDate = new Map(p.series.map((s) => [s[0], s]));
  }

  // ---------- 絞り込み ----------
  function filters() {
    const [wmin, wmax] = ($("#f-weight").value || "0-1e9").split("-").map(Number);
    return {
      range: Number($("#f-range").value),
      kind: $("#f-kind").value,
      variety: $("#f-variety").value,
      pref: $("#f-pref").value,
      ship: $("#f-ship").value,
      wmin, wmax,
      q: $("#f-q").value.trim().toLowerCase(),
    };
  }

  function filteredProducts(f) {
    return D.products.filter((p) =>
      (!f.kind || (p.kind || "生果") === f.kind) &&
      (!f.variety || p.variety === f.variety) &&
      (!f.pref || p.prefecture === f.pref) &&
      (f.ship === "" || String(p.ship) === f.ship) &&
      (!$("#f-weight").value || (p.weight && p.weight >= f.wmin && p.weight < f.wmax)) &&
      (!f.q || (p.title + " " + p.producer).toLowerCase().includes(f.q)));
  }

  function rangeDates(f) {
    const all = D.daily.map((d) => d.date);
    if (!f.range) return all;
    const start = addDays(D.latest_date, -f.range + 1);
    return all.filter((d) => d >= start);
  }

  function dailyAgg(products, dates) {
    return dates.map((d) => {
      const ppks = [], prices = [];
      let sales = 0, listed = 0, out = 0;
      for (const p of products) {
        const s = p.byDate.get(d);
        if (!s) continue;
        listed++;
        if (s[5]) { out++; } else {
          if (s[2]) ppks.push(s[2]);
          if (s[1]) prices.push(s[1]);
        }
        if (s[4]) sales += s[4];
      }
      return {
        date: d, listed, available: listed - out,
        soldout: listed ? out / listed : null,
        p25: quantile(ppks, 0.25), med: quantile(ppks, 0.5), p75: quantile(ppks, 0.75),
        price: quantile(prices, 0.5), sales,
      };
    });
  }

  // ---------- Chart.js 共通 ----------
  function baseOptions(extra = {}) {
    return Object.assign({
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { color: css("--text-2"), boxWidth: 12, boxHeight: 12, usePointStyle: true } },
        tooltip: { backgroundColor: css("--surface"), titleColor: css("--text"), bodyColor: css("--text-2"), borderColor: css("--border"), borderWidth: 1, padding: 10 },
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: css("--muted"), maxRotation: 0, autoSkipPadding: 16 }, border: { color: css("--border") } },
        y: { grid: { color: css("--grid") }, ticks: { color: css("--muted") }, border: { display: false } },
      },
    }, extra);
  }

  function draw(id, config) {
    if (charts[id]) charts[id].destroy();
    charts[id] = new Chart(document.getElementById(id), config);
  }
  const shortDate = (d) => d.slice(5).replace("-", "/");

  // ---------- KPI ----------
  function renderKpis(agg) {
    const last = agg[agg.length - 1] || {};
    const weekAgo = agg.length > 7 ? agg[agg.length - 8] : null;
    const last7 = agg.slice(-7).map((a) => a.sales);
    const prev7 = agg.slice(-14, -7).map((a) => a.sales);
    const s7 = mean(last7), sp = mean(prev7);
    const delta = (cur, prev, fmt) => (cur != null && prev ? `7日前 ${fmt(prev)}（${pctTxt((cur - prev) / prev)}）` : "前週比データなし");
    const tiles = [
      ["販売中の商品数", num(last.available), "<small>件</small>", `掲載 ${num(last.listed)} 件`],
      ["1kgあたり価格（中央値）", yen(last.med), "", delta(last.med, weekAgo && weekAgo.med, yen)],
      ["商品価格（中央値）", yen(last.price), "", delta(last.price, weekAgo && weekAgo.price, yen)],
      ["推定販売数/日（7日平均）", num(s7, 1), "<small>個</small>", sp ? `前の7日 ${num(sp, 1)}（${pctTxt((s7 - sp) / sp)}）` : "前週比データなし"],
      ["売り切れ率", last.soldout == null ? "–" : (last.soldout * 100).toFixed(1), "<small>%</small>", `売り切れ ${num(last.listed - last.available)} 件`],
    ];
    $("#kpis").innerHTML = tiles.map(([l, v, u, d]) =>
      `<div class="kpi"><div class="label">${l}</div><div class="value">${v}${u}</div><div class="delta">${d}</div></div>`).join("");
  }

  // ---------- 推移チャート ----------
  function renderTrends(agg) {
    const labels = agg.map((a) => shortDate(a.date));
    const pr = agg.length < 5 ? 4 : 0; // データが数日分しかない間は点で表示する
    draw("c-ppk", {
      type: "line",
      data: {
        labels,
        datasets: [
          { label: "25パーセンタイル", data: agg.map((a) => a.p25), borderWidth: 0, pointRadius: 0, fill: false },
          { label: "25〜75%の幅", data: agg.map((a) => a.p75), borderWidth: 0, pointRadius: 0, backgroundColor: css("--series-1-soft"), fill: "-1" },
          { label: "中央値", data: agg.map((a) => a.med), borderColor: css("--series-1"), backgroundColor: css("--series-1"), borderWidth: 2, pointRadius: pr, pointHoverRadius: 4, tension: 0.2 },
        ],
      },
      options: baseOptions({
        plugins: Object.assign(baseOptions().plugins, {
          legend: { labels: { color: css("--text-2"), boxWidth: 12, filter: (i) => i.datasetIndex > 0 } },
          tooltip: Object.assign(baseOptions().plugins.tooltip, {
            callbacks: { label: (c) => ` ${c.datasetIndex === 1 ? "75パーセンタイル" : c.dataset.label}: ${yen(c.parsed.y)}/kg` },
          }),
        }),
        scales: Object.assign(baseOptions().scales, { y: Object.assign(baseOptions().scales.y, { ticks: { color: css("--muted"), callback: (v) => yen(v) } }) }),
      }),
    });

    const ma = agg.map((_, i) => {
      const w = agg.slice(Math.max(0, i - 6), i + 1).map((a) => a.sales);
      return w.length === 7 ? mean(w) : null;
    });
    draw("c-sales", {
      type: "bar",
      data: {
        labels,
        datasets: [
          { type: "line", label: "7日移動平均", data: ma, borderColor: css("--series-1"), backgroundColor: css("--series-1"), borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: 0.2 },
          { label: "日次", data: agg.map((a) => a.sales), backgroundColor: css("--series-1-soft"), hoverBackgroundColor: css("--series-1"), borderRadius: { topLeft: 3, topRight: 3 }, barPercentage: 0.9, categoryPercentage: 0.9 },
        ],
      },
      options: baseOptions({
        plugins: Object.assign(baseOptions().plugins, {
          tooltip: Object.assign(baseOptions().plugins.tooltip, { callbacks: { label: (c) => ` ${c.dataset.label}: ${num(c.parsed.y, 1)} 個` } }),
        }),
      }),
    });
  }

  // ---------- レコメンド ----------
  function recommend(products, weight) {
    const W = D.config.price_band_width;
    let pool = products.filter((p) => p.active && p.ppk14);
    let comparable = pool;
    let scope = "絞り込み条件に合う全商品";
    if (weight) {
      const near = pool.filter((p) => p.weight && p.weight >= weight / 2 && p.weight <= weight * 2);
      if (near.length >= 12) { comparable = near; scope = `内容量 ${num(weight / 2)}g〜${num(weight * 2)}g の商品`; }
    }
    if (comparable.length < 5) return { error: `比較できる商品が ${comparable.length} 件しかありません。絞り込み条件を緩めてください。` };

    const map = new Map();
    for (const p of comparable) {
      const b = Math.floor(p.ppk14 / W);
      if (!map.has(b)) map.set(b, []);
      map.get(b).push(p);
    }
    const keys = [...map.keys()].sort((a, b) => a - b);
    const bands = [];
    for (let b = keys[0]; b <= keys[keys.length - 1]; b++) {
      const items = map.get(b) || [];
      const pace = items.length ? mean(items.map((p) => p.sales14)) : null;
      bands.push({ lo: b * W, hi: (b + 1) * W, mid: (b + 0.5) * W, n: items.length, pace, revenue: pace == null ? null : pace * (b + 0.5) * W });
    }

    const noSales = comparable.every((p) => !p.sales14);
    const minN = comparable.length >= 30 ? 3 : 2;
    let peak = 0, cliff = null;
    for (const band of bands) {
      if (band.n < minN || band.pace == null) continue;
      if (peak > 0 && band.pace < peak * 0.6) { cliff = band; break; }
      peak = Math.max(peak, band.pace);
    }
    const eligible = bands.filter((b) => b.n >= minN && (!cliff || b.lo < cliff.lo));
    const best = eligible.reduce((a, b) => (a && a.revenue >= b.revenue ? a : b), null);
    const ppks = comparable.map((p) => p.ppk14);
    return {
      scope, n: comparable.length, bands, minN, noSales,
      best: noSales ? null : best, cliff: noSales ? null : cliff,
      p25: quantile(ppks, 0.25), p50: quantile(ppks, 0.5), p75: quantile(ppks, 0.75), ppks,
    };
  }

  function renderReco(products) {
    const weight = Number($("#r-weight").value) || null;
    const cur = Number($("#r-price").value) || null;
    const r = recommend(products, weight);
    const out = $("#reco-out");
    if (r.error) { out.innerHTML = `<p class="reco-text">${esc(r.error)}</p>`; renderBands(null); return r; }

    const w = weight || 1000;
    const toPrice = (ppk) => round10((ppk * w) / 1000);
    const boxes = [];
    if (r.best) {
      boxes.push(`<div class="reco-box main"><div class="label">推奨価格（${num(w)}g）</div>
        <div class="big">${yen(toPrice(r.best.mid))}</div>
        <div class="sub2">推奨帯 ${yen(toPrice(r.best.lo))}〜${yen(toPrice(r.best.hi))}（${yen(r.best.lo)}〜${yen(r.best.hi)}/kg）</div></div>`);
    }
    if (r.noSales) {
      boxes.push(`<div class="reco-box main"><div class="label">推奨価格</div><div class="big">データ蓄積中</div>
        <div class="sub2">販売ペースは前日との差分から推定するため、2日目以降に表示されます。精度が出るのは2〜3週間後です。</div></div>`);
    }
    boxes.push(r.noSales ? `<div class="reco-box"><div class="label">売れ行き急落ライン</div><div class="big">データ蓄積中</div><div class="sub2">2日目以降に表示</div></div>` : r.cliff
      ? `<div class="reco-box warn"><div class="label">売れ行き急落ライン</div>
          <div class="big">${yen(toPrice(r.cliff.lo))}</div>
          <div class="sub2">${yen(r.cliff.lo)}/kg を超えると販売ペースが ${Math.round((1 - r.cliff.pace / Math.max(...r.bands.filter((b) => b.lo < r.cliff.lo && b.n >= r.minN).map((b) => b.pace))) * 100)}% 低下</div></div>`
      : `<div class="reco-box"><div class="label">売れ行き急落ライン</div><div class="big">検出なし</div>
          <div class="sub2">価格帯による大きな落ち込みは見られません</div></div>`);
    boxes.push(`<div class="reco-box"><div class="label">市場相場（${num(w)}g換算）</div>
      <div class="big">${yen(toPrice(r.p50))}</div>
      <div class="sub2">中央50%: ${yen(toPrice(r.p25))}〜${yen(toPrice(r.p75))}</div></div>`);

    const notes = [`比較対象: ${esc(r.scope)}（${r.n} 件、直近14日の平均値）`];
    if (r.best) notes.push(`1kgあたり ${yen(r.best.lo)}〜${yen(r.best.hi)} の帯が「価格 × 販売ペース」で最も売上が大きくなっています（${r.best.n} 商品・平均 ${num(r.best.pace, 2)} 個/日）。`);
    if (cur) {
      const ppk = (cur / w) * 1000;
      const rank = r.ppks.filter((v) => v <= ppk).length / r.ppks.length;
      let msg = `現在価格 ${yen(cur)}（${yen(ppk)}/kg）は比較商品の中で安い方から ${Math.round(rank * 100)}% の位置です。`;
      if (r.cliff && ppk >= r.cliff.lo) msg += ` <strong>急落ライン（${yen(toPrice(r.cliff.lo))}）を超えています。${yen(toPrice(r.cliff.lo) - 10)} 以下への値下げを検討してください。</strong>`;
      else if (r.best && ppk < r.best.lo) msg += ` 推奨帯より安く、<strong>${yen(toPrice(r.best.lo))} 程度まで値上げしても販売ペースを保てる可能性</strong>があります。`;
      else if (r.best && ppk >= r.best.hi) msg += ` 推奨帯より高めです。販売数が伸びない場合は ${yen(toPrice(r.best.mid))} 前後を目安に調整してください。`;
      else if (r.best) msg += ` 推奨帯の範囲内で、適正な価格設定です。`;
      notes.push(msg);
    }
    out.innerHTML = boxes.join("") + `<ul class="reco-text">${notes.map((n) => `<li>${n}</li>`).join("")}</ul>`;
    renderBands(r);
    return r;
  }

  function renderBands(r) {
    if (!r) { if (charts["c-band"]) charts["c-band"].destroy(); return; }
    const colors = r.bands.map((b) =>
      r.best && b.lo === r.best.lo ? css("--series-2") : r.cliff && b.lo >= r.cliff.lo ? css("--muted") : css("--series-1"));
    draw("c-band", {
      type: "bar",
      data: {
        labels: r.bands.map((b) => `${num(b.lo / 1000, 1)}〜${num(b.hi / 1000, 1)}千`),
        datasets: [{ label: "平均販売数/日", data: r.bands.map((b) => b.pace), backgroundColor: colors, borderRadius: { topLeft: 4, topRight: 4 }, categoryPercentage: 0.9, barPercentage: 0.92 }],
      },
      options: baseOptions({
        interaction: { mode: "nearest", intersect: false, axis: "x" },
        plugins: Object.assign(baseOptions().plugins, {
          legend: { display: false },
          tooltip: Object.assign(baseOptions().plugins.tooltip, {
            callbacks: {
              title: (c) => { const b = r.bands[c[0].dataIndex]; return `${yen(b.lo)}〜${yen(b.hi)} /kg`; },
              label: (c) => {
                const b = r.bands[c.dataIndex];
                const tag = r.best && b.lo === r.best.lo ? "（推奨帯）" : r.cliff && b.lo >= r.cliff.lo ? "（急落ライン以上）" : "";
                return [` 平均 ${num(b.pace, 2)} 個/日 ${tag}`, ` 商品数 ${b.n} 件${b.n < r.minN ? "（少数のため参考値）" : ""}`];
              },
            },
          }),
        }),
        scales: Object.assign(baseOptions().scales, { x: Object.assign(baseOptions().scales.x, { title: { display: true, text: "1kgあたり価格（円）", color: css("--muted") } }) }),
      }),
    });
  }

  function renderScatter(products) {
    const pts = products.filter((p) => p.active && p.ppk14);
    const mk = (arr) => arr.map((p) => ({ x: p.ppk14, y: p.sales14, p }));
    const own = pts.filter((p) => p.own);
    const datasets = [{ label: "他の商品", data: mk(pts.filter((p) => !p.own)), backgroundColor: css("--series-1"), borderColor: css("--surface"), borderWidth: 1.5, pointRadius: 5, pointHoverRadius: 7 }];
    if (own.length) datasets.push({ label: "自社商品", data: mk(own), backgroundColor: css("--series-2"), borderColor: css("--surface"), borderWidth: 1.5, pointRadius: 7, pointHoverRadius: 9 });
    draw("c-scatter", {
      type: "scatter",
      data: { datasets },
      options: baseOptions({
        interaction: { mode: "nearest", intersect: true },
        plugins: Object.assign(baseOptions().plugins, {
          legend: { display: own.length > 0, labels: { color: css("--text-2"), boxWidth: 10 } },
          tooltip: Object.assign(baseOptions().plugins.tooltip, {
            callbacks: {
              title: (c) => c[0].raw.p.title,
              label: (c) => [` ${yen(c.raw.p.price)}・${c.raw.p.weight ? num(c.raw.p.weight) + "g" : "内容量不明"}`, ` ${yen(c.raw.x)}/kg・${num(c.raw.y, 2)} 個/日`],
            },
          }),
        }),
        scales: {
          x: Object.assign(baseOptions().scales.x, { grid: { color: css("--grid") }, title: { display: true, text: "1kgあたり価格（円）", color: css("--muted") }, ticks: { color: css("--muted"), callback: (v) => yen(v) } }),
          y: Object.assign(baseOptions().scales.y, { beginAtZero: true, title: { display: true, text: "推定販売数/日", color: css("--muted") } }),
        },
        onClick: (_, els) => { if (els.length) showDetail(datasets[els[0].datasetIndex].data[els[0].index].p.id); },
      }),
    });
  }

  // ---------- 商品テーブル ----------
  let tableRows = [];
  function renderTable(products) {
    const onlyActive = $("#f-active").checked;
    const { k, asc } = state.sort;
    tableRows = products.filter((p) => !onlyActive || p.active).sort((a, b) => {
      const x = a[k], y = b[k];
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      const c = typeof x === "string" ? x.localeCompare(y, "ja") : x - y;
      return asc ? c : -c;
    });
    $("#p-count").textContent = `${tableRows.length} 件`;
    document.querySelectorAll("#p-table th[data-k]").forEach((th) => {
      th.classList.toggle("sorted", th.dataset.k === k);
      th.classList.toggle("asc", th.dataset.k === k && asc);
    });
    $("#p-table tbody").innerHTML = tableRows.map((p) => {
      const status = !p.active ? `<span class="tag">掲載終了</span>` : p.sold_out ? `<span class="tag out">売り切れ</span>` : p.stock != null ? `<span class="tag">残り${p.stock}</span>` : /reservation/.test(p.status_label || "") ? `<span class="tag">予約受付</span>` : `<span class="tag">販売中</span>`;
      const chg = p.pchg == null || p.pchg === 0 ? "–" : `<span class="${p.pchg > 0 ? "up" : "down"}">${pctTxt(p.pchg)}</span>`;
      return `<tr data-id="${esc(p.id)}" class="${p.own ? "own" : ""} ${state.selected === p.id ? "selected" : ""}">
        <td class="title"><a href="${esc(p.url)}" target="_blank" rel="noopener">${esc(p.title)}</a>${p.ship ? ' <span class="tag">送料込</span>' : ""}</td>
        <td>${esc(p.producer)}</td><td>${esc(p.prefecture)}</td><td>${esc(p.variety) || "–"}</td>
        <td class="num">${num(p.rank)}</td>
        <td class="num">${yen(p.price)}</td>
        <td class="num">${p.ship && !p.fee ? "込" : yen(p.fee)}</td>
        <td class="num">${p.weight ? num(p.weight) + "g" : "–"}${p.west ? ' <span class="est">推計</span>' : ""}</td>
        <td class="num">${yen(p.ppk)}</td><td class="num">${chg}</td>
        <td class="num">${num(p.sales7, 2)}</td><td class="num">${num(p.sales30, 2)}</td>
        <td class="num">${num(p.reviews)}</td><td>${status}</td></tr>`;
    }).join("");
  }

  function renderEvents(products, f) {
    const ids = new Set(products.map((p) => p.id));
    const start = f.range ? addDays(D.latest_date, -f.range + 1) : "";
    const rows = D.price_events.filter((e) => ids.has(e.id) && e.date >= start).slice(0, 150);
    $("#e-table tbody").innerHTML = rows.length ? rows.map((e) => {
      const pc = (e.new - e.old) / e.old;
      const sc = e.before && e.after != null ? (e.after - e.before) / e.before : null;
      return `<tr><td>${e.date}</td><td class="title">${esc(e.title)}</td>
        <td class="num">${yen(e.old)}</td><td class="num">${yen(e.new)}</td>
        <td class="num"><span class="${pc > 0 ? "up" : "down"}">${pctTxt(pc)}</span></td>
        <td class="num">${num(e.before, 2)}</td><td class="num">${num(e.after, 2)}</td>
        <td class="num">${sc == null ? "–" : `<span class="${sc < 0 ? "up" : "down"}">${pctTxt(sc)}</span>`}</td></tr>`;
    }).join("") : `<tr><td colspan="8">この条件での価格改定はありません</td></tr>`;
  }

  // ---------- 商品詳細 ----------
  function showDetail(id) {
    const p = D.products.find((x) => x.id === id);
    if (!p) return;
    state.selected = id;
    const f = filters();
    const dates = new Set(rangeDates(f));
    const s = p.series.filter((r) => dates.has(r[0]));
    $("#detail-card").hidden = false;
    $("#detail-title").textContent = p.title;
    $("#detail-meta").innerHTML = `${esc(p.producer)}・${esc(p.prefecture)}・${esc(p.variety) || "品種不明"}・現在 ${yen(p.price)}（${yen(p.ppk)}/kg）・<a href="${esc(p.url)}" target="_blank" rel="noopener">食べチョクで見る</a>`;
    const labels = s.map((r) => shortDate(r[0]));
    const line = (label, data, fmt) => ({
      type: "line",
      data: { labels, datasets: [{ label, data, borderColor: css("--series-1"), backgroundColor: css("--series-1"), borderWidth: 2, pointRadius: s.length < 5 ? 4 : 0, pointHoverRadius: 4, stepped: label === "価格" }] },
      options: baseOptions({
        plugins: Object.assign(baseOptions().plugins, {
          legend: { display: false },
          tooltip: Object.assign(baseOptions().plugins.tooltip, { callbacks: { label: (c) => ` ${label}: ${fmt(c.parsed.y)}` } }),
        }),
      }),
    });
    draw("c-d-price", line("価格", s.map((r) => r[1]), yen));
    // レビュー増加ベースの推定は1件で大きく跳ねるため、7日移動平均で表示する
    const ma = s.map((_, i) => {
      const w = s.slice(Math.max(0, i - 6), i + 1).map((r) => r[4]).filter((v) => v != null);
      return w.length ? mean(w) : null;
    });
    draw("c-d-sales", line("推定販売数/日（7日平均）", ma, (v) => num(v, 2) + " 個"));
    document.querySelectorAll("#p-table tbody tr").forEach((tr) => tr.classList.toggle("selected", tr.dataset.id === id));
    $("#detail-card").scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ---------- CSV ----------
  function downloadCsv() {
    const cols = [["id", "商品ID"], ["title", "商品名"], ["producer", "生産者"], ["prefecture", "産地"], ["variety", "品種"], ["rank", "掲載順"], ["price", "価格"], ["fee", "送料"], ["ship", "送料込"], ["weight", "内容量g"], ["ppk", "円/kg"], ["price_7d", "7日前価格"], ["sales7", "販売/日(7日)"], ["sales14", "販売/日(14日)"], ["sales30", "販売/日(30日)"], ["reviews", "レビュー数"], ["rating", "評価"], ["sold_out", "売り切れ"], ["url", "URL"]];
    const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const body = [cols.map((c) => q(c[1])).join(",")].concat(tableRows.map((p) => cols.map((c) => q(p[c[0]])).join(","))).join("\r\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["﻿" + body], { type: "text/csv" }));
    a.download = `ichigo_${D.latest_date}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  // ---------- 描画 ----------
  function renderAll() {
    const f = filters();
    const products = filteredProducts(f);
    const agg = dailyAgg(products, rangeDates(f));
    renderKpis(agg);
    renderTrends(agg);
    renderReco(products);
    renderScatter(products);
    renderTable(products);
    renderEvents(products, f);
    if (state.selected && !$("#detail-card").hidden) {
      const y = window.scrollY;
      showDetail(state.selected);
      window.scrollTo(0, y);
    }
  }

  document.querySelectorAll(".filters select, .filters input").forEach((el) => el.addEventListener("input", renderAll));
  $("#f-active").addEventListener("change", () => renderTable(filteredProducts(filters())));
  ["#r-weight", "#r-price"].forEach((s) => $(s).addEventListener("input", () => renderReco(filteredProducts(filters()))));
  $("#p-table thead").addEventListener("click", (e) => {
    const th = e.target.closest("th[data-k]");
    if (!th) return;
    const k = th.dataset.k;
    state.sort = { k, asc: state.sort.k === k ? !state.sort.asc : ["title", "producer", "prefecture", "variety", "status"].includes(k) };
    renderTable(filteredProducts(filters()));
  });
  $("#p-table tbody").addEventListener("click", (e) => {
    if (e.target.closest("a")) return;
    const tr = e.target.closest("tr[data-id]");
    if (tr) showDetail(tr.dataset.id);
  });
  $("#detail-close").addEventListener("click", () => {
    $("#detail-card").hidden = true;
    state.selected = null;
    document.querySelectorAll("#p-table tr.selected").forEach((tr) => tr.classList.remove("selected"));
  });
  $("#csv").addEventListener("click", downloadCsv);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", renderAll);

  renderAll();
})();
