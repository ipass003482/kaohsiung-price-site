"use strict";

const API_ENDPOINT = "https://data.moa.gov.tw/Service/OpenData/FromM/FarmTransData.aspx";
const SOURCE_PAGE = "https://data.moa.gov.tw/open_detail.aspx?id=037";
const MARKET_NAMES = ["高雄市", "鳳山區"];
const CATEGORY_NAMES = { N04: "蔬菜", N05: "水果" };
const CATEGORY_FILTERS = { N04: "vegetable", N05: "fruit" };
const NON_PRODUCT_BUCKET_NAMES = new Set(["其他"]);

const appState = {
  records: [],
  selectedMarket: "all",
  selectedCategory: "all",
  searchTerm: "",
  latestDate: "",
  fetchedAt: null,
  failedMarkets: [],
  loading: false,
};

const retailState = {
  snapshot: null,
  searchTerm: "",
  category: "all",
  loading: true,
  error: false,
};

const livestockState = {
  snapshot: null,
  loading: true,
  error: false,
};

const elements = {
  connectionStatus: document.querySelector("#connection-status"),
  statusLight: document.querySelector("#status-light"),
  latestDate: document.querySelector("#latest-date"),
  fetchTime: document.querySelector("#fetch-time"),
  itemCount: document.querySelector("#item-count"),
  resultsLabel: document.querySelector("#results-label"),
  priceList: document.querySelector("#price-list"),
  searchInput: document.querySelector("#search-input"),
  refreshButton: document.querySelector("#refresh-button"),
  wholesaleView: document.querySelector("#wholesale-view"),
  livestockView: document.querySelector("#livestock-view"),
  livestockRefreshButton: document.querySelector("#livestock-refresh-button"),
  livestockLatestDate: document.querySelector("#livestock-latest-date"),
  livestockUpdated: document.querySelector("#livestock-updated"),
  livestockMarketCount: document.querySelector("#livestock-market-count"),
  livestockResultsLabel: document.querySelector("#livestock-results-label"),
  livestockPriceList: document.querySelector("#livestock-price-list"),
  poultryDate: document.querySelector("#poultry-date"),
  poultryPriceList: document.querySelector("#poultry-price-list"),
  cattleDate: document.querySelector("#cattle-date"),
  cattlePriceList: document.querySelector("#cattle-price-list"),
  sheepDate: document.querySelector("#sheep-date"),
  sheepPriceList: document.querySelector("#sheep-price-list"),
  retailView: document.querySelector("#retail-view"),
  retailUpdated: document.querySelector("#retail-updated"),
  retailSourceNotice: document.querySelector("#retail-source-notice"),
  retailPriceList: document.querySelector("#retail-price-list"),
  retailResultsLabel: document.querySelector("#retail-results-label"),
  retailSearchInput: document.querySelector("#retail-search-input"),
  pxmartStatus: document.querySelector("#pxmart-status"),
  carrefourStatus: document.querySelector("#carrefour-status"),
};

function taipeiToday() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return new Date(Date.UTC(Number(values.year), Number(values.month) - 1, Number(values.day), 12));
}

function formatRocDate(date) {
  const year = String(date.getUTCFullYear() - 1911).padStart(3, "0");
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  return `${year}.${month}.${day}`;
}

function getDateRange(days = 14) {
  const end = taipeiToday();
  const start = new Date(end);
  start.setUTCDate(start.getUTCDate() - (days - 1));
  return { start: formatRocDate(start), end: formatRocDate(end) };
}

function dateNumber(dateString) {
  const [year, month, day] = String(dateString || "").split(".").map(Number);
  return (year || 0) * 10000 + (month || 0) * 100 + (day || 0);
}

function displayDate(dateString, short = false) {
  const [rocYear, month, day] = String(dateString || "").split(".");
  if (!rocYear || !month || !day) return "—";
  return short ? `${Number(month)}/${Number(day)}` : `${Number(rocYear) + 1911}/${month}/${day}`;
}

function safeNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function normalizeRecord(raw) {
  const category = String(raw["種類代碼"] || "");
  const name = String(raw["作物名稱"] || "").trim();
  const averagePrice = safeNumber(raw["平均價"]);
  const volume = safeNumber(raw["交易量"]);
  if (!CATEGORY_NAMES[category] || !name || NON_PRODUCT_BUCKET_NAMES.has(name) || name === "休市" || averagePrice <= 0 || volume <= 0) return null;

  return {
    date: String(raw["交易日期"] || ""),
    dateNumber: dateNumber(raw["交易日期"]),
    category,
    categoryName: CATEGORY_NAMES[category],
    cropCode: String(raw["作物代號"] || ""),
    name,
    market: String(raw["市場名稱"] || ""),
    averagePrice,
    volume,
  };
}

async function fetchMarket(market, range) {
  const params = new URLSearchParams({
    IsTransData: "1",
    UnitId: "037",
    StartDate: range.start,
    EndDate: range.end,
    Market: market,
  });
  params.set("$top", "5000");
  params.set("$skip", "0");
  const response = await fetch(`${API_ENDPOINT}?${params.toString()}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`行情服務回應 ${response.status}`);
  const payload = await response.json();
  if (!Array.isArray(payload)) throw new Error("行情資料格式不符");
  return payload.map(normalizeRecord).filter(Boolean);
}

function setConnectionStatus(message, state = "ready") {
  elements.connectionStatus.textContent = message;
  elements.statusLight.className = `status-light${state === "loading" ? " is-loading" : ""}`;
  elements.connectionStatus.parentElement.classList.toggle("is-error", state === "error");
  elements.connectionStatus.parentElement.classList.toggle("is-loading", state === "loading");
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function marketListForSelection() {
  return appState.selectedMarket === "all" ? MARKET_NAMES : [appState.selectedMarket];
}

function buildProducts() {
  const groups = new Map();
  for (const record of appState.records) {
    const key = `${record.category}|${record.cropCode || record.name}|${record.name}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(record);
  }

  const products = [];
  const selectedMarkets = marketListForSelection();
  for (const [key, records] of groups) {
    const [category] = key.split("|");
    if (appState.selectedCategory !== "all" && CATEGORY_FILTERS[category] !== appState.selectedCategory) continue;
    const marketPrices = selectedMarkets.map((market) => {
      const latest = records
        .filter((record) => record.market === market)
        .sort((left, right) => right.dateNumber - left.dateNumber || right.volume - left.volume)[0];
      return { market, record: latest || null };
    });
    if (!marketPrices.some(({ record }) => record)) continue;

    const name = records[0].name;
    const aliases = name === "甘藍" ? "高麗菜 包心菜" :
      name.includes("番茄") || name.includes("蕃茄") ? "番茄 蕃茄 小番茄" :
      name === "胡瓜" ? "小黃瓜" :
      name === "番石榴" ? "芭樂" :
      name === "青蔥" ? "蔥" : "";
    const searchText = `${name} ${CATEGORY_NAMES[category]} ${aliases}`.toLocaleLowerCase("zh-Hant");
    if (appState.searchTerm && !searchText.includes(appState.searchTerm.toLocaleLowerCase("zh-Hant"))) continue;

    products.push({
      name,
      category,
      categoryName: CATEGORY_NAMES[category],
      searchKey: name,
      marketPrices,
      latestVolume: Math.max(...marketPrices.map(({ record }) => record?.volume || 0)),
    });
  }

  return products.sort((left, right) => right.latestVolume - left.latestVolume || left.name.localeCompare(right.name, "zh-Hant"));
}

function renderPriceCard(product) {
  const marketPrices = product.marketPrices.map(({ market, record }) => {
    if (!record) {
      return `<div class="market-price"><span class="market-name">${escapeHtml(market)}</span><strong class="market-amount empty">—</strong><span class="market-date">近14日無成交價格</span></div>`;
    }
    const price = record.averagePrice.toLocaleString("zh-TW", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const volume = Math.round(record.volume).toLocaleString("zh-TW");
    return `<div class="market-price">
      <span class="market-name">${escapeHtml(market)}</span>
      <strong class="market-amount">$${price}<span class="market-unit">/公斤</span></strong>
      <span class="market-date">最近成交 ${displayDate(record.date, true)}</span>
    </div>`;
  }).join("");
  const totalVolume = Math.round(product.latestVolume).toLocaleString("zh-TW");
  const kindClass = product.category === "N05" ? " fruit" : "";

  return `<article class="price-card" data-product="${escapeHtml(product.searchKey)}">
    <div class="product-top">
      <h4 class="product-title">${escapeHtml(product.name)}</h4>
      <span class="product-category${kindClass}">${escapeHtml(product.categoryName)}</span>
    </div>
    <div class="market-price-grid${product.marketPrices.length === 1 ? " single" : ""}">${marketPrices}</div>
      <div class="card-meta"><span>批發平均價 · 元<span class="unit-emphasis">／公斤</span></span><span>單一市場交易量 ${totalVolume} kg</span></div>
  </article>`;
}

function renderEmptyState(title, message) {
  elements.priceList.innerHTML = `<div class="empty-state"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(message)}</span></div>`;
}

function formatRetailTime(value, includeYear = false) {
  if (!value) return "尚未更新";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "尚未更新";
  return new Intl.DateTimeFormat("zh-TW", {
    timeZone: "Asia/Taipei",
    year: includeYear ? "numeric" : undefined,
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function renderSourceStatus(element, source) {
  if (!element) return;
  const count = source?.product_count || 0;
  const status = source?.status || "pending";
  const labels = {
    ok: `有 ${count} 項商品`,
    partial: `找到 ${count} 項`,
    stale: `保留 ${count} 項上次價格`,
    empty: "目前沒找到",
    error: "暫時讀不到",
    pending: "正在整理價格",
  };
  element.textContent = labels[status] || labels.pending;
  element.className = `source-badge ${status === "ok" ? "connected" : ["partial", "stale"].includes(status) ? "partial" : status === "error" ? "pending" : "planning"}`;
}

function retailSourceDate(source) {
  return source?.collected_at || (["ok", "partial"].includes(source?.status) ? retailState.snapshot?.collected_at : null);
}

function renderRetailSourceNotice(sources) {
  const messages = Object.values(sources).filter((source) => source.status === "stale").map((source) =>
    `${source.name}更新暫停，先顯示 ${formatRetailTime(retailSourceDate(source), true)} 的價格。`
  );
  elements.retailSourceNotice.textContent = messages.length ? `${messages.join(" ")}售價與庫存請以賣場為準。` : "";
  elements.retailSourceNotice.hidden = messages.length === 0;
}

function compareRetailCandidates(left, right) {
  const leftUnitPrice = Number(left.price_per_kg);
  const rightUnitPrice = Number(right.price_per_kg);
  const leftHasUnitPrice = Number.isFinite(leftUnitPrice) && leftUnitPrice > 0;
  const rightHasUnitPrice = Number.isFinite(rightUnitPrice) && rightUnitPrice > 0;
  if (leftHasUnitPrice && rightHasUnitPrice) return leftUnitPrice - rightUnitPrice || left.price - right.price;
  if (leftHasUnitPrice) return -1;
  if (rightHasUnitPrice) return 1;
  return left.price - right.price;
}

function retailProductIcon(name, category) {
  const value = String(name || "");
  if (category === "meat") {
    if (/鴨/.test(value)) return "🦆";
    if (/雞|全雞/.test(value)) return "🍗";
    if (/羊/.test(value)) return "🍖";
    if (/豬/.test(value)) return "🥓";
    if (/牛/.test(value)) return "🥩";
    return "🛒";
  }
  const foodIcons = {
    "小白菜": `<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M23.4 25.7C15.2 27.1 8.3 21.2 9.1 13.8c7.2-2.2 13.1.5 15.6 7.8Z" fill="#69B84F"/>
    <path d="M23.6 23.8C18 16.2 20.1 8.1 26 5.3c6.2 5.1 7.4 12.7 1.7 19.5Z" fill="#4F9D43"/>
    <path d="M25 25.2c2.4-8.1 9.8-12.4 15.7-9.4.1 7.4-4.8 12.5-14.8 13Z" fill="#7BC95A"/>
    <path d="M23.8 22.7c-2.2 5.7-6.3 11.4-8 17.3 2.3 2.3 5.8 2.5 9 .6 1-6.3 1.1-12.3.7-17.3Z" fill="#F7F5DF" stroke="#D8E4C7" stroke-width="1.2"/>
    <path d="M25.4 21.3c-.8 6.6.2 13.2.7 19.2 2.7 1.6 5.7 1.3 7.8-.9-1.7-7-3.9-13.5-6.9-19Z" fill="#F7F5DF" stroke="#D8E4C7" stroke-width="1.2"/>
    <path d="M14 15.2c4.1.8 7 3.1 8.9 6.4M25.7 17.7c.2-4 1.1-6.6 2.4-8.6m3.9 13.8c1.4-3.3 3.5-5.4 6.3-6.7" stroke="#3F8D3D" stroke-width="1.35" stroke-linecap="round"/>
  </svg>`,
    "小黃瓜": `<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M11.3 39.4c-2.1-2.2-.7-6.1 2.1-10.3 4.4-6.7 12.2-15.3 18.8-20.1 3.7-2.7 7-2.2 8.7.5 1.8 2.8.5 6.2-2.3 10.1-4.7 6.5-12.4 14.3-19 19.2-3.6 2.7-6.4 2.8-8.3.6Z" fill="#438F3D" stroke="#347C36" stroke-width="1.2"/>
    <path d="M15 35.8c5.8-7.5 13.8-16.1 22-22.9" stroke="#8BCB62" stroke-width="2.2" stroke-linecap="round"/>
    <path d="m36.8 9.3 3-3.1 2.6 1.7-1.9 3.7" fill="#5BA947"/>
    <path d="M17.9 29.3l1.1-1.1m2.4 5.1 1.1-1.1m1.4-8.1 1.1-1.1m2.4 5.1 1.1-1.1m1.2-8.1 1.1-1.1m2.5 5.1 1-1.1" stroke="#B7DC83" stroke-width="1.4" stroke-linecap="round"/>
    <circle cx="12.5" cy="38" r="5.2" fill="#EAF2CE" stroke="#438F3D" stroke-width="1.5"/>
    <circle cx="12.5" cy="38" r="3.5" stroke="#9BCB67" stroke-width="1"/>
    <circle cx="11.2" cy="36.8" r=".65" fill="#6A9D45"/><circle cx="13.7" cy="36.9" r=".65" fill="#6A9D45"/><circle cx="12.5" cy="39.2" r=".65" fill="#6A9D45"/>
  </svg>`,
    "奇異果": "🥝",
    "芭樂": `<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M11 27c-1-7 3-13 10-15 2-5 8-7 12-3 7 0 12 6 11 13-1 9-8 17-18 18C17 41 12 35 11 27Z" fill="#79B94D" stroke="#528F39" stroke-width="1.4"/>
    <path d="M14 24c0-5 3-9 8-11" stroke="#B2D87A" stroke-width="2" stroke-linecap="round"/>
    <path d="M24 27c0-5 3-8 8-8 5 0 8 4 7 9-1 5-5 8-10 8-4 0-6-4-5-9Z" fill="#FFF6DC" stroke="#528F39" stroke-width="1.4"/>
    <path d="M29 22c-2 3-2 9 0 13m4-12c-2 3-2 8 0 11" stroke="#F0B6A5" stroke-width="1.1" stroke-linecap="round"/>
    <circle cx="28" cy="27" r=".75" fill="#9E8355"/><circle cx="34" cy="27" r=".75" fill="#9E8355"/><circle cx="31" cy="31" r=".75" fill="#9E8355"/>
    <path d="M22 12c-3-4-2-7 1-9 4 2 5 5 3 9" fill="#4D963E"/>
  </svg>`,
    "柳橙": "🍊",
    "香蕉": "🍌",
    "鳳梨": "🍍",
    "蘋果": "🍎",
    "玉米筍": "🌽",
    "杏鮑菇": "🍄",
    "空心菜": "🥬",
    "金針菇": "🍄",
    "青江菜": "🥬",
    "青花菜": "🥦",
    "青蔥": `<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M19 27C12 20 10 12 13 6c7 5 10 12 10 20ZM24 25C21 17 23 9 28 4c5 7 5 15 1 23ZM28 29c3-8 9-13 15-12-1 8-6 14-14 18Z" fill="#57A949" stroke="#438D3E" stroke-width="1.1" stroke-linejoin="round"/>
    <path d="M19 24c0 6-2 11-2 16 2 3 5 3 7 0l2-15m-1-2c1 7 2 12 2 17 2 3 5 2 6 0l-3-16" fill="#F7F4DF" stroke="#BDD39F" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M17 41 14 44m7-3-1 4m8-4 1 4m4-5 3 3" stroke="#A58C65" stroke-width="1.2" stroke-linecap="round"/>
  </svg>`,
    "洋蔥": "🧅",
    "紅蘿蔔": "🥕",
    "香菇": "🍄",
    "高麗菜": "🥬",
    "番茄": "🍅",
    "絲瓜": `<svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
    <path d="M10 38c-2-2-1-6 2-10 4-6 12-14 19-19 4-3 7-2 9 0 2 3 1 6-2 10-5 7-13 15-19 20-4 3-7 2-9-1Z" fill="#75B94D" stroke="#4C943A" stroke-width="1.3"/>
    <path d="M13 36c6-8 14-16 24-24M17 39c5-7 13-15 22-22M10 32c6-8 14-16 22-23" stroke="#C1DF83" stroke-width="1.4" stroke-linecap="round"/>
    <path d="m37 9 3-4 3 2-2 4" fill="#559D40"/>
    <circle cx="11.5" cy="38" r="5" fill="#F2F1D9" stroke="#4C943A" stroke-width="1.3"/><circle cx="11.5" cy="38" r="2.4" fill="#DCE8B6"/>
  </svg>`,
    "萵苣": "🥬",
  };
  // Unknown names stay neutral until an exact food icon is assigned.
  return foodIcons[value] || "🛒";
}

function renderRetailOffer(sourceId, source, candidates) {
  const sourceName = source?.name || (sourceId === "pxmart" ? "全聯小時達" : "家樂福線上購物");
  const brandMark = sourceId === "pxmart" ? "PX" : "家";
  const brandClass = sourceId === "pxmart" ? "pxmart" : "carrefour";
  const stale = source?.status === "stale";
  const priceDate = retailSourceDate(source);
  const dateLabel = priceDate ? `<small class="offer-data-date${stale ? " is-stale" : ""}">${stale ? "上次價格" : "價格日期"} ${escapeHtml(formatRetailTime(priceDate, true))}${stale ? " · 更新暫停" : ""}</small>` : "";
  const sourceHeading = `<div class="offer-source-row"><span class="offer-store-mark ${brandClass}" aria-hidden="true">${brandMark}</span><span class="offer-source">${escapeHtml(sourceName)}</span></div>${dateLabel}`;
  if (!candidates.length) {
    const missingMessage = stale ? "上次資料未收錄這項商品" : source?.status === "error" ? "價格暫時無法更新" : "這次沒有找到這項商品";
    return `<div class="retail-offer not-listed">${sourceHeading}<div class="offer-missing"><strong>—</strong><small>${missingMessage}</small></div></div>`;
  }
  const sortedCandidates = [...candidates].sort(compareRetailCandidates);
  const renderCandidate = (product, extra = false) => {
    const price = Number(product.price).toLocaleString("zh-TW", { maximumFractionDigits: 2 });
    const hasUnitPrice = Number.isFinite(Number(product.price_per_kg)) && Number(product.price_per_kg) > 0;
    const unit = hasUnitPrice
      ? `約 NT$${Number(product.price_per_kg).toLocaleString("zh-TW", { maximumFractionDigits: 1 })}<span class="unit-emphasis">／公斤</span>`
      : "依包裝售價比較";
    const name = product.url
      ? `<a class="offer-product-name" href="${escapeHtml(product.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(product.name)} <span aria-hidden="true">↗</span></a>`
      : `<span class="offer-product-name">${escapeHtml(product.name)}</span>`;
    return `<div class="offer-candidate${extra ? " extra" : ""}">
      <div class="offer-candidate-copy">${name}<small>${unit}</small></div>
      <strong class="offer-price">NT$${price}</strong>
    </div>`;
  };
  const visibleCandidate = renderCandidate(sortedCandidates[0]);
  const additionalCandidates = sortedCandidates.slice(1);
  const moreCandidates = additionalCandidates.length
    ? `<details class="offer-more"><summary>其他規格 ${additionalCandidates.length} 款</summary>${additionalCandidates.map((product) => renderCandidate(product, true)).join("")}</details>`
    : "";

  return `<div class="retail-offer${stale ? " is-stale" : ""}">${sourceHeading}<div class="offer-candidate-list">${visibleCandidate}${moreCandidates}</div></div>`;
}

function renderRetailPrices() {
  const snapshot = retailState.snapshot;
  elements.retailSourceNotice.hidden = true;
  if (retailState.loading) {
    elements.retailPriceList.innerHTML = '<div class="loading-card"><span class="loader" aria-hidden="true"></span><span>正在找兩家賣場的價格…</span></div>';
    elements.retailResultsLabel.textContent = "找價格中…";
    return;
  }

  if (retailState.error || !snapshot) {
    elements.retailUpdated.textContent = "價格準備中";
    elements.pxmartStatus.textContent = "價格整理中";
    elements.carrefourStatus.textContent = "價格整理中";
    elements.pxmartStatus.className = "source-badge planning";
    elements.carrefourStatus.className = "source-badge planning";
    renderRetailEmpty("價格還在準備中", "稍後再來看看，賣場商品價格整理好就會出現在這裡。");
    return;
  }

  const sources = snapshot.sources || {};
  renderSourceStatus(elements.pxmartStatus, sources.pxmart);
  renderSourceStatus(elements.carrefourStatus, sources.carrefour);
  elements.retailUpdated.textContent = snapshot.collected_at ? `最近檢查 ${formatRetailTime(snapshot.collected_at)}` : "價格準備中";
  renderRetailSourceNotice(sources);

  if (!snapshot.collected_at && !(snapshot.products || []).length) {
    renderRetailEmpty("目前還沒有商品價格", "全聯與家樂福價格整理好後，會顯示在這裡。");
    return;
  }

  const groups = new Map();
  for (const product of snapshot.products || []) {
    if (retailState.category !== "all" && product.category !== retailState.category) continue;
    const key = product.canonical || product.name;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(product);
  }

  const searchTerm = retailState.searchTerm.toLocaleLowerCase("zh-Hant");
  const products = [...groups.entries()]
    .filter(([key, variants]) => !searchTerm || `${key} ${variants.map((item) => item.name).join(" ")}`.toLocaleLowerCase("zh-Hant").includes(searchTerm))
    .sort((left, right) => left[0].localeCompare(right[0], "zh-Hant"));
  elements.retailResultsLabel.textContent = `${products.length} 項食材`;

  if (products.length === 0) {
    renderRetailEmpty("這次沒有找到合適商品", retailState.searchTerm ? "換個食材名稱試試，或清除搜尋條件看看全部品項。" : "晚一點再來看看，賣場商品會定時更新。");
    return;
  }

  const sourceIds = ["pxmart", "carrefour"];
  elements.retailPriceList.innerHTML = products.map(([canonical, variants]) => {
    const category = variants[0].category === "fruit" ? "水果" : variants[0].category === "meat" ? "肉類" : "蔬菜";
    const className = variants[0].category === "fruit" ? " fruit" : variants[0].category === "meat" ? " meat" : "";
    const icon = retailProductIcon(canonical, variants[0].category);
    const offers = sourceIds.map((sourceId) => renderRetailOffer(
      sourceId,
      sources[sourceId],
      variants.filter((item) => item.source === sourceId),
    )).join("");
    return `<article class="retail-price-card">
      <div class="retail-product-heading"><span class="retail-food-icon${className}" aria-hidden="true">${icon}</span><div class="retail-product-name"><h4>${escapeHtml(canonical)}</h4><span>${category}</span></div></div>
      <div class="retail-offer-grid">${offers}</div>
    </article>`;
  }).join("");
}

function renderRetailEmpty(title, message) {
  elements.retailPriceList.innerHTML = `<div class="empty-state"><strong>${escapeHtml(title)}</strong><span>${escapeHtml(message)}</span></div>`;
  elements.retailResultsLabel.textContent = "—";
}

async function loadRetailSnapshot() {
  retailState.loading = true;
  renderRetailPrices();
  try {
    const snapshotUrl = new URL("data/retail-prices.json", document.baseURI);
    snapshotUrl.searchParams.set("v", String(Date.now()));
    const response = await fetch(snapshotUrl, { cache: "no-store" });
    if (!response.ok) throw new Error(`價格快照回應 ${response.status}`);
    retailState.snapshot = await response.json();
    retailState.error = false;
  } catch {
    retailState.snapshot = null;
    retailState.error = true;
  }
  retailState.loading = false;
  renderRetailPrices();
}

function displayLivestockDate(dateString) {
  const value = String(dateString || "").replaceAll(".", "");
  if (!/^\d{7}$/.test(value)) return "—";
  return `${Number(value.slice(0, 3)) + 1911}/${Number(value.slice(3, 5))}/${Number(value.slice(5, 7))}`;
}

function displayShortLivestockDate(dateString) {
  const value = String(dateString || "").replaceAll(".", "");
  if (!/^\d{7}$/.test(value)) return "—";
  return `${Number(value.slice(3, 5))}/${Number(value.slice(5, 7))}`;
}

function displayShortIsoDate(dateString) {
  const match = String(dateString || "").match(/^\d{4}-(\d{2})-(\d{2})$/);
  return match ? `${Number(match[1])}/${Number(match[2])}` : "—";
}

function renderLivestockPrices() {
  const { snapshot } = livestockState;
  if (livestockState.loading) {
    elements.livestockPriceList.innerHTML = '<div class="loading-card"><span class="loader" aria-hidden="true"></span><span>正在讀取肉品行情…</span></div>';
    elements.poultryPriceList.innerHTML = '<div class="loading-card"><span class="loader" aria-hidden="true"></span><span>正在讀取雞肉行情…</span></div>';
    elements.cattlePriceList.innerHTML = '<div class="loading-card"><span class="loader" aria-hidden="true"></span><span>正在讀取牛隻行情…</span></div>';
    elements.sheepPriceList.innerHTML = '<div class="loading-card"><span class="loader" aria-hidden="true"></span><span>正在讀取羊隻行情…</span></div>';
    elements.livestockResultsLabel.textContent = "讀取中…";
    return;
  }

  if (livestockState.error || !snapshot) {
    elements.livestockLatestDate.textContent = "暫無資料";
    elements.livestockUpdated.textContent = "行情快照尚未建立";
    elements.livestockMarketCount.textContent = "0";
    elements.livestockPriceList.innerHTML = '<div class="empty-state"><strong>目前無法讀取肉品行情</strong><span>請稍後重新讀取；資料服務暫時無法回應時，這裡不會用估價填補。</span></div>';
    elements.poultryDate.textContent = "—";
    elements.poultryPriceList.innerHTML = '<div class="empty-state"><strong>目前無法讀取雞肉行情</strong><span>請稍後重新讀取官方行情快照。</span></div>';
    elements.cattleDate.textContent = "—";
    elements.cattlePriceList.innerHTML = '<div class="empty-state"><strong>目前無法讀取牛隻行情</strong><span>請稍後重新讀取官方行情快照。</span></div>';
    elements.sheepDate.textContent = "—";
    elements.sheepPriceList.innerHTML = '<div class="empty-state"><strong>目前無法讀取羊隻行情</strong><span>請稍後重新讀取官方行情快照。</span></div>';
    elements.livestockResultsLabel.textContent = "—";
    return;
  }

  const records = [...(snapshot.records || [])].sort((left, right) => {
    const dateOrder = String(right.trade_date || "").localeCompare(String(left.trade_date || ""));
    return dateOrder || String(left.market || "").localeCompare(String(right.market || ""), "zh-Hant");
  });
  const latestDate = records[0]?.trade_date_roc || "";
  elements.livestockLatestDate.textContent = latestDate ? displayLivestockDate(latestDate) : "暫無資料";
  elements.livestockUpdated.textContent = snapshot.collected_at ? `快照更新 ${formatRetailTime(snapshot.collected_at)}` : "快照更新時間 —";
  elements.livestockMarketCount.textContent = String(records.length);
  elements.livestockResultsLabel.textContent = `${records.length} 個市場`;

  if (!records.length) {
    elements.livestockPriceList.innerHTML = '<div class="empty-state"><strong>近期沒有毛豬交易資料</strong><span>各肉品市場交易日不同；有新交易資料後才會顯示價格。</span></div>';
  } else {
    elements.livestockPriceList.innerHTML = records.map((record) => {
      const averagePrice = Number(record.standard_pig_avg_price_per_kg);
      const priceText = averagePrice > 0 ? `$${averagePrice.toLocaleString("zh-TW", { maximumFractionDigits: 2 })}` : "—";
      const count = Number(record.standard_pig_count) || 0;
      const weight = Number(record.standard_pig_avg_weight_kg) || 0;
      return `<article class="price-card livestock-price-card">
        <div class="product-top"><h4 class="product-title">${escapeHtml(record.market)}</h4><span class="product-category meat">豬肉</span></div>
        <div class="market-price-grid single"><div class="market-price">
          <span class="market-name">規格豬拍賣均價</span>
          <strong class="market-amount">${priceText}<span class="market-unit">/公斤</span></strong>
          <span class="market-date">交易日 ${escapeHtml(displayShortLivestockDate(record.trade_date_roc))}</span>
        </div></div>
        <div class="card-meta"><span>毛豬成交均價 · 元<span class="unit-emphasis">／公斤</span></span><span>${count.toLocaleString("zh-TW")} 頭 · 平均 ${weight.toLocaleString("zh-TW", { maximumFractionDigits: 1 })} kg</span></div>
      </article>`;
    }).join("");
  }

  const chicken = snapshot.poultry_reference;
  if (!chicken || Number(chicken.price_per_catty) <= 0) {
    elements.poultryDate.textContent = "—";
    elements.poultryPriceList.innerHTML = '<div class="empty-state"><strong>近期沒有雞肉門市行情</strong><span>官方資料有回報價格後才會顯示，不會用估價填補。</span></div>';
  } else {
    const chickenPrice = Number(chicken.price_per_catty);
    const chickenPerKg = Number(chicken.price_per_kg);
    elements.poultryDate.textContent = `資料日 ${displayShortIsoDate(chicken.date)}`;
    elements.poultryPriceList.innerHTML = `<article class="price-card poultry-price-card">
      <div class="product-top"><h4 class="product-title">${escapeHtml(chicken.name)}・${escapeHtml(chicken.market_label)}</h4><span class="product-category meat">雞肉</span></div>
      <div class="market-price-grid single"><div class="market-price">
        <span class="market-name">官方高屏門市參考價</span>
        <strong class="market-amount">$${chickenPrice.toLocaleString("zh-TW", { maximumFractionDigits: 2 })}<span class="market-unit">/台斤</span></strong>
        <span class="market-date">約 $${chickenPerKg.toLocaleString("zh-TW", { maximumFractionDigits: 1 })}<span class="unit-emphasis">／公斤</span></span>
      </div></div>
      <div class="card-meta"><span>資料日 ${escapeHtml(displayShortIsoDate(chicken.date))}</span><span>農業部家禽行情</span></div>
    </article>`;
  }

  const cattleRecords = [...(snapshot.cattle_records || [])].sort((left, right) => String(left.name || "").localeCompare(String(right.name || ""), "zh-Hant"));
  const latestCattleDate = cattleRecords.reduce((latest, record) => String(record.date || "") > latest ? String(record.date || "") : latest, "");
  elements.cattleDate.textContent = latestCattleDate ? `週起 ${displayShortIsoDate(latestCattleDate)}` : "—";
  if (!cattleRecords.length) {
    elements.cattlePriceList.innerHTML = '<div class="empty-state"><strong>近期沒有牛隻產地行情</strong><span>官方週行情有回報後才會顯示；此來源不是牛肉分切零售價。</span></div>';
  } else {
    elements.cattlePriceList.innerHTML = cattleRecords.map((record) => {
      const price = Number(record.price) || 0;
      const perHead = record.unit === "元／頭";
      return `<article class="price-card livestock-price-card">
        <div class="product-top"><h4 class="product-title">${escapeHtml(record.name)}</h4><span class="product-category meat">牛隻</span></div>
        <div class="market-price-grid single"><div class="market-price">
          <span class="market-name">活牛產地週均價</span>
          <strong class="market-amount">$${price.toLocaleString("zh-TW", { maximumFractionDigits: 2 })}<span class="market-unit">/${perHead ? "頭" : "公斤"}</span></strong>
          <span class="market-date">週起 ${escapeHtml(displayShortIsoDate(record.date))}</span>
        </div></div>
        <div class="card-meta"><span>中央畜產會 · 全台週行情</span><span>${perHead ? "幼牛單頭價" : "活體產地價"}</span></div>
      </article>`;
    }).join("");
  }

  const sheepRecords = [...(snapshot.sheep_records || [])].sort((left, right) => {
    const marketOrder = String(left.market || "").localeCompare(String(right.market || ""), "zh-Hant");
    return marketOrder || String(left.name || "").localeCompare(String(right.name || ""), "zh-Hant");
  });
  const latestSheepDate = sheepRecords.reduce((latest, record) => String(record.date || "") > latest ? String(record.date || "") : latest, "");
  elements.sheepDate.textContent = latestSheepDate ? `最近交易 ${displayShortIsoDate(latestSheepDate)}` : "—";
  if (!sheepRecords.length) {
    elements.sheepPriceList.innerHTML = '<div class="empty-state"><strong>近 30 天沒有羊隻拍賣資料</strong><span>彰化、雲林市場休市或未交易時不會補上估價。</span></div>';
  } else {
    const sheepByMarket = new Map();
    for (const record of sheepRecords) {
      const key = `${record.market}|${record.date}`;
      if (!sheepByMarket.has(key)) sheepByMarket.set(key, { market: record.market, date: record.date, records: [] });
      sheepByMarket.get(key).records.push(record);
    }
    elements.sheepPriceList.innerHTML = [...sheepByMarket.values()].map((market) => {
      const prices = market.records.map((record) => {
        const price = Number(record.price_per_kg) || 0;
        const heads = Number(record.head_count) || 0;
        return `<div class="market-price">
          <span class="market-name">${escapeHtml(record.name)}</span>
          <strong class="market-amount">$${price.toLocaleString("zh-TW", { maximumFractionDigits: 2 })}<span class="market-unit">/公斤</span></strong>
          <span class="market-date">${heads.toLocaleString("zh-TW")} 頭</span>
        </div>`;
      }).join("");
      return `<article class="price-card livestock-price-card">
        <div class="product-top"><h4 class="product-title">${escapeHtml(market.market)}羊隻拍賣</h4><span class="product-category meat">羊隻</span></div>
        <div class="market-price-grid">${prices}</div>
        <div class="card-meta"><span>交易日 ${escapeHtml(displayShortIsoDate(market.date))}</span><span>拍賣成交價 · 元<span class="unit-emphasis">／公斤</span></span></div>
      </article>`;
    }).join("");
  }
}

async function loadLivestockSnapshot() {
  livestockState.loading = true;
  elements.livestockRefreshButton.disabled = true;
  elements.livestockRefreshButton.classList.add("is-loading");
  renderLivestockPrices();
  try {
    const snapshotUrl = new URL("data/livestock-prices.json", document.baseURI);
    snapshotUrl.searchParams.set("v", String(Date.now()));
    const response = await fetch(snapshotUrl, { cache: "no-store" });
    if (!response.ok) throw new Error(`肉品行情快照回應 ${response.status}`);
    livestockState.snapshot = await response.json();
    livestockState.error = false;
  } catch {
    livestockState.snapshot = null;
    livestockState.error = true;
  }
  livestockState.loading = false;
  elements.livestockRefreshButton.disabled = false;
  elements.livestockRefreshButton.classList.remove("is-loading");
  renderLivestockPrices();
}

function render() {
  const latest = appState.records.reduce((current, record) => record.dateNumber > current.dateNumber ? record : current, { dateNumber: 0, date: "" });
  appState.latestDate = latest.date;
  elements.latestDate.textContent = latest.date ? displayDate(latest.date) : "暫無資料";
  elements.fetchTime.textContent = appState.fetchedAt
    ? `查詢時間 ${new Intl.DateTimeFormat("zh-TW", { timeZone: "Asia/Taipei", hour: "2-digit", minute: "2-digit", hour12: false }).format(appState.fetchedAt)}`
    : "查詢時間 —";

  const products = buildProducts();
  elements.itemCount.textContent = products.length.toLocaleString("zh-TW");
  elements.resultsLabel.textContent = `${products.length} 個品項`;

  if (appState.loading) {
    elements.priceList.innerHTML = '<div class="loading-card"><span class="loader" aria-hidden="true"></span><span>正在整理最新行情…</span></div>';
    return;
  }
  if (appState.records.length === 0 && appState.failedMarkets.length === MARKET_NAMES.length) {
    renderEmptyState("目前連不上行情資料", "請確認網路後按「更新行情」重試。官方資料服務暫時無法回應時，這裡不會顯示舊價或估價。");
    return;
  }
  if (products.length === 0) {
    renderEmptyState("近14日沒有有效成交價", appState.searchTerm ? "換個品名或清除搜尋條件看看。" : "休市或當日沒有成交時，會顯示最近一次成交價；若近14日都沒有紀錄，才會留白。");
    return;
  }

  elements.priceList.innerHTML = products.map(renderPriceCard).join("");
}

async function loadPrices() {
  if (appState.loading) return;
  appState.loading = true;
  elements.refreshButton.disabled = true;
  elements.refreshButton.classList.add("is-loading");
  setConnectionStatus("正在連線農業部行情…", "loading");
  render();

  const range = getDateRange(14);
  const settled = await Promise.allSettled(MARKET_NAMES.map((market) => fetchMarket(market, range)));
  const records = [];
  const failedMarkets = [];
  settled.forEach((result, index) => {
    if (result.status === "fulfilled") records.push(...result.value);
    else failedMarkets.push(MARKET_NAMES[index]);
  });

  appState.records = records;
  appState.failedMarkets = failedMarkets;
  appState.fetchedAt = new Date();
  appState.loading = false;
  elements.refreshButton.disabled = false;
  elements.refreshButton.classList.remove("is-loading");

  if (failedMarkets.length === MARKET_NAMES.length) {
    setConnectionStatus("目前無法連線行情服務", "error");
  } else if (failedMarkets.length > 0) {
    setConnectionStatus(`已連線，${failedMarkets.join("、")}暫時無資料`, "ready");
  } else {
    setConnectionStatus("已連線農業部開放資料", "ready");
  }
  render();
}

function setActiveButtons(selector, attribute, value) {
  document.querySelectorAll(selector).forEach((button) => {
    const active = button.dataset[attribute] === value;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

document.querySelectorAll(".mode-tab").forEach((button) => {
  button.addEventListener("click", () => {
    const modeViews = {
      wholesale: elements.wholesaleView,
      livestock: elements.livestockView,
      retail: elements.retailView,
    };
    document.querySelectorAll(".mode-tab").forEach((tab) => {
      const active = tab === button;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-selected", String(active));
    });
    Object.entries(modeViews).forEach(([mode, view]) => {
      view.hidden = mode !== button.dataset.mode;
    });
  });
});

document.querySelectorAll(".filter-chip").forEach((button) => {
  button.addEventListener("click", () => {
    appState.selectedMarket = button.dataset.market;
    setActiveButtons(".filter-chip", "market", appState.selectedMarket);
    render();
  });
});

document.querySelectorAll(".category-chip").forEach((button) => {
  button.addEventListener("click", () => {
    appState.selectedCategory = button.dataset.category;
    setActiveButtons(".category-chip", "category", appState.selectedCategory);
    render();
  });
});

elements.searchInput.addEventListener("input", (event) => {
  appState.searchTerm = event.target.value.trim();
  render();
});

elements.retailSearchInput.addEventListener("input", (event) => {
  retailState.searchTerm = event.target.value.trim();
  renderRetailPrices();
});

document.querySelectorAll("[data-retail-category]").forEach((button) => {
  button.addEventListener("click", () => {
    retailState.category = button.dataset.retailCategory;
    document.querySelectorAll("[data-retail-category]").forEach((chip) => {
      const active = chip === button;
      chip.classList.toggle("is-active", active);
      chip.setAttribute("aria-pressed", String(active));
    });
    renderRetailPrices();
  });
});

elements.refreshButton.addEventListener("click", loadPrices);
elements.livestockRefreshButton.addEventListener("click", loadLivestockSnapshot);
document.addEventListener("keydown", (event) => {
  if (event.key === "/" && !["INPUT", "TEXTAREA"].includes(document.activeElement?.tagName)) {
    event.preventDefault();
    if (!elements.retailView.hidden) elements.retailSearchInput.focus();
    else if (!elements.livestockView.hidden) elements.livestockRefreshButton.focus();
    else elements.searchInput.focus();
  }
  if (event.key === "Escape" && [elements.searchInput, elements.retailSearchInput].includes(document.activeElement)) {
    const activeInput = document.activeElement;
    activeInput.value = "";
    if (activeInput === elements.searchInput) {
      appState.searchTerm = "";
      render();
    } else {
      retailState.searchTerm = "";
      renderRetailPrices();
    }
    activeInput.blur();
  }
});

// Open data is refreshed by the source daily. The user can refresh on demand;
// this client-side call avoids storing credentials or copied prices in the site.
loadPrices();
loadLivestockSnapshot();
loadRetailSnapshot();
