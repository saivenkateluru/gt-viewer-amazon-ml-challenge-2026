"use strict";

const state = { filtered: [], selectedId: null, selectedMatchId: null, request: null };

const elements = {
  description: document.querySelector("#dataset-description"),
  metrics: document.querySelector("#metrics"),
  search: document.querySelector("#search-input"),
  country: document.querySelector("#country-filter"),
  match: document.querySelector("#match-filter"),
  sort: document.querySelector("#sort-filter"),
  count: document.querySelector("#result-count"),
  list: document.querySelector("#result-list"),
  badges: document.querySelector("#entity-badges"),
  name: document.querySelector("#entity-name"),
  address: document.querySelector("#entity-address"),
  graph: document.querySelector("#graph"),
  comparison: document.querySelector("#comparison"),
};

const escapeXml = (value) => String(value ?? "").replace(/[<>&'\"]/g, (character) => ({
  "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;",
}[character]));

const truncate = (value, limit) => {
  const text = value || "Missing value";
  return text.length > limit ? `${text.slice(0, limit - 1)}…` : text;
};

function metric(value, label) {
  return `<div class="metric"><strong>${escapeXml(value)}</strong><span>${escapeXml(label)}</span></div>`;
}

function renderMetadata(metadata) {
  elements.description.textContent = metadata.description;
  elements.metrics.innerHTML = [
    metric(metadata.groupCount.toLocaleString(), "Source 1 entities"),
    metric(metadata.recordCount.toLocaleString(), "Total records"),
    metric(metadata.singletonCount.toLocaleString(), "Singletons"),
    metric(Object.keys(metadata.countries).length, "Countries"),
  ].join("");

  Object.entries(metadata.countries).forEach(([country, count]) => {
    const option = document.createElement("option");
    option.value = country;
    option.textContent = `${country} (${count})`;
    elements.country.append(option);
  });
}

async function applyFilters() {
  state.request?.abort();
  state.request = new AbortController();
  const parameters = new URLSearchParams({
    q: elements.search.value.trim(),
    country: elements.country.value,
    match: elements.match.value,
    sort: elements.sort.value,
    limit: "40",
  });
  elements.count.textContent = "Searching…";
  try {
    const response = await fetch(`/api/entities?${parameters}`, { signal: state.request.signal });
    if (!response.ok) throw new Error(`Search failed (HTTP ${response.status})`);
    const payload = await response.json();
    state.filtered = payload.groups;
    elements.count.textContent = payload.hasMore
      ? `First ${state.filtered.length} results`
      : `${state.filtered.length} ${state.filtered.length === 1 ? "entity" : "entities"}`;
  } catch (error) {
    if (error.name === "AbortError") return;
    state.filtered = [];
    elements.count.textContent = "Search failed";
    elements.list.innerHTML = `<div class="empty-results">${escapeXml(error.message)}</div>`;
    return;
  }
  if (!state.filtered.some((group) => group.source1.id === state.selectedId)) {
    state.selectedId = (state.filtered.find((group) => group.matches.length) || state.filtered[0])?.source1.id ?? null;
    state.selectedMatchId = null;
  }
  renderList();
  renderSelected();
}

function renderList() {
  elements.list.replaceChildren();
  if (!state.filtered.length) {
    const empty = document.createElement("div");
    empty.className = "empty-results";
    empty.textContent = "No entities match these filters.";
    elements.list.append(empty);
    return;
  }

  state.filtered.forEach((group) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `result-item${group.source1.id === state.selectedId ? " active" : ""}`;
    button.setAttribute("role", "option");
    button.setAttribute("aria-selected", String(group.source1.id === state.selectedId));
    const top = document.createElement("span");
    top.className = "result-topline";
    top.innerHTML = `<span>${escapeXml(group.source1.id)}</span><span>${group.matches.length} ${group.matches.length === 1 ? "match" : "matches"}</span>`;
    const name = document.createElement("strong");
    name.textContent = group.source1.name || "Unnamed business";
    const address = document.createElement("span");
    address.textContent = group.source1.address || "No address supplied";
    button.append(top, name, address);
    button.addEventListener("click", () => selectGroup(group.source1.id));
    elements.list.append(button);
  });
}

function selectGroup(entityId) {
  state.selectedId = entityId;
  const group = selectedGroup();
  state.selectedMatchId = group?.matches[0]?.id ?? null;
  renderList();
  renderSelected();
}

function selectedGroup() {
  return state.filtered.find((group) => group.source1.id === state.selectedId);
}

function renderSelected() {
  const group = selectedGroup();
  if (!group) {
    elements.badges.replaceChildren();
    elements.name.textContent = "No entity selected";
    elements.address.textContent = "Adjust the filters to continue.";
    elements.graph.innerHTML = '<div class="empty-graph"><div><strong>No results</strong>Try a broader search or clear the filters.</div></div>';
    elements.comparison.innerHTML = '<div class="comparison-placeholder">No records to compare.</div>';
    return;
  }
  elements.badges.innerHTML = `<span class="badge s1">${escapeXml(group.source1.id)}</span><span class="badge neutral">${escapeXml(group.source1.country || "Unknown")}</span><span class="badge neutral">${group.matches.length ? `${group.matches.length} verified ${group.matches.length === 1 ? "match" : "matches"}` : "Singleton"}</span>`;
  elements.name.textContent = group.source1.name || "Unnamed business";
  elements.address.textContent = group.source1.address || "No address supplied";
  renderGraph(group);
  renderComparison(group);
}

function graphNode(record, x, y, active = false) {
  const width = record.source === "S1" ? 230 : 215;
  const height = 78;
  const color = record.source === "S1" ? "#3973e6" : record.source === "S2" ? "#e78b35" : "#2f9a79";
  return `<g class="node ${record.source.toLowerCase()}${active ? " active" : ""}" data-id="${escapeXml(record.id)}" transform="translate(${x - width / 2} ${y - height / 2})" tabindex="0" role="button" aria-label="${escapeXml(record.source)} record ${escapeXml(record.name)}">
    <rect width="${width}" height="${height}" rx="10"></rect>
    <text x="14" y="20" class="source-label" fill="${color}">${escapeXml(record.source)}</text>
    <text x="14" y="42" class="name-label">${escapeXml(truncate(record.name, 30))}</text>
    <text x="14" y="61" class="id-label">${escapeXml(record.id)}</text>
  </g>`;
}

function sidePositions(records, x) {
  if (!records.length) return [];
  const top = 70;
  const bottom = 490;
  const step = records.length === 1 ? 0 : Math.min(105, (bottom - top) / (records.length - 1));
  const height = step * (records.length - 1);
  const start = 280 - height / 2;
  return records.map((record, index) => ({ record, x, y: start + index * step }));
}

function renderGraph(group) {
  if (!group.matches.length) {
    elements.graph.innerHTML = `<div class="empty-graph"><div><strong>Singleton entity</strong>No Source 2 or Source 3 ground-truth matches.</div></div>`;
    return;
  }
  const center = { x: 500, y: 280 };
  const nodes = [
    ...sidePositions(group.matches.filter((record) => record.source === "S2"), 170),
    ...sidePositions(group.matches.filter((record) => record.source === "S3"), 830),
  ];
  const edges = nodes.map((node) => `<line class="graph-edge" x1="${center.x}" y1="${center.y}" x2="${node.x}" y2="${node.y}"></line>`).join("");
  const matchNodes = nodes.map((node) => graphNode(node.record, node.x, node.y, node.record.id === state.selectedMatchId)).join("");
  elements.graph.innerHTML = `<svg viewBox="0 0 1000 560" preserveAspectRatio="xMidYMid meet" aria-label="Ground-truth relationship graph">${edges}${graphNode(group.source1, center.x, center.y)}${matchNodes}</svg>`;
  elements.graph.querySelectorAll(".node").forEach((node) => {
    const activate = () => {
      const id = node.dataset.id;
      if (id !== group.source1.id) state.selectedMatchId = id;
      renderGraph(group);
      renderComparison(group);
    };
    node.addEventListener("click", activate);
    node.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") activate();
    });
  });
}

function recordCard(record, label) {
  const value = (text, fallback) => escapeXml(text || fallback);
  return `<article class="record">
    <div class="record-header"><span class="source-pill ${record.source.toLowerCase()}">${escapeXml(label)}</span><strong>${escapeXml(record.id)}</strong></div>
    <dl>
      <div class="field"><dt>Business name</dt><dd>${value(record.name, "Missing")}</dd></div>
      <div class="field"><dt>Business address</dt><dd>${value(record.address, "Missing")}</dd></div>
      <div class="field"><dt>Country</dt><dd>${value(record.country, "Missing")}</dd></div>
    </dl>
  </article>`;
}

function renderComparison(group) {
  if (!group.matches.length) {
    elements.comparison.innerHTML = `${recordCard(group.source1, "Reference · Source 1")}<div class="comparison-placeholder">This record has no ground-truth match.</div>`;
    return;
  }
  const match = group.matches.find((record) => record.id === state.selectedMatchId) || group.matches[0];
  state.selectedMatchId = match.id;
  elements.comparison.innerHTML = recordCard(group.source1, "Reference · Source 1") + recordCard(match, `Verified match · Source ${match.source.slice(1)}`);
}

function moveSelection(offset) {
  if (!state.filtered.length) return;
  const current = state.filtered.findIndex((group) => group.source1.id === state.selectedId);
  const next = (current + offset + state.filtered.length) % state.filtered.length;
  selectGroup(state.filtered[next].source1.id);
}

function bindEvents() {
  let searchTimer;
  elements.search.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(applyFilters, 250);
  });
  elements.country.addEventListener("change", applyFilters);
  elements.match.addEventListener("change", applyFilters);
  elements.sort.addEventListener("change", applyFilters);
  document.querySelector("#clear-button").addEventListener("click", () => {
    elements.search.value = "";
    elements.country.value = "all";
    elements.match.value = "all";
    elements.sort.value = "default";
    applyFilters();
  });
  document.querySelector("#random-button").addEventListener("click", () => {
    if (state.filtered.length) selectGroup(state.filtered[Math.floor(Math.random() * state.filtered.length)].source1.id);
  });
  document.querySelector("#previous-button").addEventListener("click", () => moveSelection(-1));
  document.querySelector("#next-button").addEventListener("click", () => moveSelection(1));
}

async function start() {
  bindEvents();
  try {
    const response = await fetch("/api/stats");
    if (!response.ok) throw new Error(`Stats failed (HTTP ${response.status})`);
    renderMetadata(await response.json());
    await applyFilters();
  } catch (error) {
    elements.description.textContent = "The local dataset index could not be loaded.";
    elements.graph.innerHTML = `<div class="empty-graph"><div><strong>Unable to load data</strong>${escapeXml(error.message)}</div></div>`;
  }
}

start();
