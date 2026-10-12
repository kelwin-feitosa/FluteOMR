"use strict";

const $ = (id) => document.getElementById(id);
const state = {
  token: null, pages: [], page: null, image: null, decisions: {}, revision: 0,
  selected: null, filter: "all", zoom: 1, overlays: true, dirty: false,
  drawMode: false, drawStart: null, draftRegion: null, screen: "home",
};
const kindNames = { treble: "Clave de sol", bass: "Clave de fá", alto: "Clave de dó", other: "Outra clave" };
const diagnosis = {
  multiple_plausible_components: "O detector encontrou mais de um componente plausível e não escolheu uma região. Nenhum candidato geométrico foi salvo nas sugestões.",
};

function toast(message) {
  const node = $("toast");
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { node.hidden = true; }, 4500);
}

async function jsonRequest(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
  return body;
}

function itemFor(staffId) {
  return state.page.view.clefs.find((item) => item.staff_id === staffId);
}

function effective(item) {
  if (state.decisions[item.staff_id]) return { ...state.decisions[item.staff_id], source: "user_correction" };
  if (item.prediction.status === "detected") {
    return { state: "present", kind: "treble", region: item.prediction.region, source: "automatic_prediction" };
  }
  return { state: "unknown", kind: null, region: null, source: "unresolved_prediction" };
}

function isPending(item) { return effective(item).state === "unknown"; }

function boxText(box) {
  if (!box) return "Não há região definida";
  return `x ${Math.round(box.left)}–${Math.round(box.right)} · y ${Math.round(box.top)}–${Math.round(box.bottom)}`;
}

function counts() {
  const clefs = state.page.view.clefs;
  return {
    detected: clefs.filter((item) => item.prediction.status === "detected").length,
    pending: clefs.filter(isPending).length,
    corrected: clefs.filter((item) => Boolean(state.decisions[item.staff_id])).length,
  };
}

function displayName(filename) {
  return filename.replace(/__[0-9a-f]{8,}_p\d+\.(png|jpe?g)$/i, "").replaceAll("_", " ").trim();
}

function renderHome() {
  const list = $("home-pages");
  list.replaceChildren();
  $("home-count").textContent = `${state.pages.length} imagem(ns) no catálogo local`;
  for (const page of state.pages) {
    const card = document.createElement("article");
    card.className = "home-card";
    const title = document.createElement("h3");
    title.textContent = displayName(page.name);
    title.title = page.name;
    const stats = document.createElement("div");
    stats.className = "home-stats";
    for (const [label, value, css] of [
      ["pautas detectadas", page.staff_count, ""],
      ["pendências conhecidas", page.pending_count, page.pending_count ? "pending" : ""],
      ["correções salvas", page.corrected_count, ""],
    ]) {
      const badge = document.createElement("span");
      badge.className = css;
      badge.textContent = `${value} ${label}`;
      stats.append(badge);
    }
    const open = document.createElement("button");
    open.type = "button";
    open.className = "primary";
    open.textContent = "Abrir no editor";
    open.setAttribute("aria-label", `Abrir ${displayName(page.name)} no editor`);
    open.addEventListener("click", () => loadPage(page.id).catch((error) => toast(error.message)));
    card.append(title, stats, open);
    list.append(card);
  }
}

async function showHome() {
  if (state.dirty && !window.confirm("Voltar ao início e descartar correções não salvas?")) return;
  const bootstrap = await jsonRequest("/api/bootstrap");
  state.token = bootstrap.token;
  state.pages = bootstrap.pages;
  if (state.drawMode) cancelDraw();
  if (state.dirty) {
    state.decisions = structuredClone(state.page.decisions);
    state.dirty = false;
  }
  state.screen = "home";
  $("editor-shell").hidden = true;
  $("home-screen").hidden = false;
  renderHome();
}

function renderSummary() {
  const n = counts();
  $("summary").textContent = `${state.page.view.clefs.length} pautas detectadas · ${n.detected} claves de sol aceitas pelo detector · ${n.pending} pendência(s) · ${n.corrected} correção(ões) do usuário.`;
  $("page-meta").textContent = `${state.page.image.width} × ${state.page.image.height} px · ${state.page.view.systems.groups.length} grupo(s) de sistema · ${state.page.view.systems.status === "ambiguous" ? "agrupamento ambíguo" : "agrupamento geométrico"}`;
  $("page-count").textContent = `${state.pages.length} imagens`;
  $("notice").textContent = state.dirty
    ? "Alterações ainda não salvas. Predições e referências de avaliação continuam intactas."
    : n.pending ? `${n.pending} clave(s) ainda exigem decisão. As caixas aceitas são predições automáticas.`
      : "Sem pendências de clave neste arquivo de correções. Predições automáticas continuam não validadas.";
  $("notice").classList.toggle("ok", n.pending === 0 && !state.dirty);
  $("save").disabled = !state.dirty;
}

function labelFor(item) {
  const value = effective(item);
  if (value.source === "user_correction") return value.state === "absent" ? "Ausência corrigida" : "Corrigida";
  if (value.state === "unknown") return "Pendente";
  return "Predição aceita";
}

function renderList() {
  const list = $("clef-list");
  list.replaceChildren();
  state.page.view.clefs.forEach((item, index) => {
    if (state.filter === "pending" && !isPending(item)) return;
    if (state.filter === "corrected" && !state.decisions[item.staff_id]) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = `clef-item ${state.selected === item.staff_id ? "selected" : ""}`;
    button.setAttribute("role", "listitem");
    const top = document.createElement("span");
    top.className = "topline";
    const name = document.createElement("strong");
    name.textContent = `Pauta ${index + 1} · ${item.staff_id}`;
    const status = document.createElement("span");
    status.className = state.decisions[item.staff_id] ? "state-corrected" : isPending(item) ? "state-pending" : "state-auto";
    status.textContent = labelFor(item);
    top.append(name, status);
    const small = document.createElement("span");
    small.className = "small";
    small.textContent = isPending(item) ? "Selecione para revisar" : kindNames[effective(item).kind] || "Nenhuma clave";
    button.append(top, small);
    button.addEventListener("click", () => selectStaff(item.staff_id, true));
    list.append(button);
  });
}

function spacing(item) { return Math.max(6, (item.staff_region.bottom - item.staff_region.top) / 4); }

function reviewZone(item) {
  const gap = spacing(item);
  const width = state.page.image.width, height = state.page.image.height;
  return {
    left: Math.max(0, Math.round(item.staff_region.left)),
    right: Math.min(width - 1, Math.round(item.staff_region.left + 12 * gap)),
    top: Math.max(0, Math.round(item.staff_region.top - 3 * gap)),
    bottom: Math.min(height - 1, Math.round(item.staff_region.bottom + 3 * gap)),
  };
}

function placeBox(element, box) {
  const projected = FluteGeometry.boxStyle(box, state.zoom);
  element.style.left = `${projected.left}px`;
  element.style.top = `${projected.top}px`;
  element.style.width = `${projected.width}px`;
  element.style.height = `${projected.height}px`;
}

function renderOverlay() {
  const layer = $("overlay-layer");
  layer.replaceChildren();
  layer.hidden = !state.overlays;
  if (!state.overlays) return;
  state.page.view.clefs.forEach((item) => {
    const value = effective(item);
    const selected = state.selected === item.staff_id;
    if (selected) {
      const staffFrame = document.createElement("div");
      staffFrame.className = "overlay staff-focus";
      placeBox(staffFrame, item.staff_region);
      layer.append(staffFrame);
    }
    const region = value.region || (isPending(item) || selected ? reviewZone(item) : null);
    if (!region) return;
    const box = document.createElement("button");
    box.type = "button";
    box.className = `overlay ${isPending(item) ? "pending" : state.decisions[item.staff_id] ? "corrected" : ""} ${selected ? "selected" : ""}`;
    box.setAttribute("aria-label", `${item.staff_id}: ${labelFor(item)}${value.region ? "" : "; zona aproximada, sem caixa detectada"}`);
    box.title = value.region ? `${item.staff_id}: ${labelFor(item)}` : `${item.staff_id}: início da pauta, sem caixa detectada`;
    placeBox(box, region);
    if (selected) {
      const label = document.createElement("span");
      label.className = "overlay-label";
      label.textContent = item.staff_id;
      box.append(label);
    }
    box.addEventListener("click", () => { if (!state.drawMode) selectStaff(item.staff_id, true); });
    layer.append(box);
  });
}

function renderCrop(item) {
  const canvas = $("crop"), context = canvas.getContext("2d");
  context.fillStyle = "#fdfcf8";
  context.fillRect(0, 0, canvas.width, canvas.height);
  const value = effective(item), zone = reviewZone(item);
  const left = Math.max(0, Math.min(zone.left, value.region?.left ?? zone.left) - 1);
  const top = Math.max(0, Math.min(zone.top, value.region?.top ?? zone.top) - 1);
  const right = Math.min(state.image.naturalWidth, Math.max(zone.right, value.region?.right ?? zone.right) + 2);
  const bottom = Math.min(state.image.naturalHeight, Math.max(zone.bottom, value.region?.bottom ?? zone.bottom) + 2);
  const sourceWidth = right - left, sourceHeight = bottom - top;
  const scale = Math.min(canvas.width / sourceWidth, canvas.height / sourceHeight);
  const offsetX = (canvas.width - sourceWidth * scale) / 2;
  const offsetY = (canvas.height - sourceHeight * scale) / 2;
  context.drawImage(state.image, left, top, sourceWidth, sourceHeight, offsetX, offsetY, sourceWidth * scale, sourceHeight * scale);
  const mark = state.draftRegion || value.region;
  if (mark) {
    context.strokeStyle = state.draftRegion ? "#c26a00" : "#4f46e5";
    context.lineWidth = 3;
    context.strokeRect(offsetX + (mark.left - left) * scale, offsetY + (mark.top - top) * scale, (mark.right - mark.left + 1) * scale, (mark.bottom - mark.top + 1) * scale);
  }
  $("crop-caption").textContent = state.draftRegion ? "Caixa em edição, ainda não aplicada." : value.region ? "Região atual sobre o recorte original." : "Início da pauta; nenhuma caixa de clave foi detectada.";
}

function renderInspector() {
  const item = itemFor(state.selected);
  $("inspector-empty").hidden = Boolean(item);
  $("inspector").hidden = !item;
  if (!item) return;
  const value = effective(item);
  const n = state.page.view.clefs.indexOf(item) + 1;
  $("selected-title").textContent = `Clave ${n} · ${item.staff_id}`;
  $("selected-badge").textContent = labelFor(item);
  $("selected-badge").className = `badge ${isPending(item) ? "pending" : state.decisions[item.staff_id] ? "corrected" : ""}`;
  $("selected-source").textContent = value.source === "user_correction" ? "Interpretação corrigida pelo usuário; o detector permanece registrado separadamente." : "Resultado do detector; ainda não é referência humana validada.";
  $("prediction-status").textContent = {
    detected: "Clave de sol detectada", inconclusive: "Inconclusivo", no_treble: "Sol não detectada",
  }[item.prediction.status] || item.prediction.status;
  $("effective-kind").textContent = value.state === "absent" ? "Nenhuma clave" : kindNames[value.kind] || "Desconhecido";
  $("effective-region").textContent = boxText(value.region);
  $("diagnostic").textContent = item.prediction.diagnostics.length
    ? item.prediction.diagnostics.map((entry) => diagnosis[entry] || `Diagnóstico: ${entry}`).join(" ")
    : "O detector não registrou motivo adicional para esta classificação.";
  $("clef-kind").value = state.decisions[item.staff_id]?.kind || value.kind || "treble";
  $("region-hint").textContent = state.drawMode
    ? "Arraste na imagem original. Esc cancela o desenho."
    : state.draftRegion ? `Região escolhida: ${boxText(state.draftRegion)}. Clique em Aplicar correção.`
      : value.region ? "A caixa atual pode ser usada ou substituída por um desenho." : "Nenhuma região disponível. Desenhe uma caixa antes de aplicar uma clave presente.";
  $("use-current").disabled = !value.region;
  $("apply-correction").disabled = !state.draftRegion;
  $("restore-auto").disabled = !state.decisions[item.staff_id];
  $("draw-region").textContent = state.drawMode ? "Cancelar desenho" : "Desenhar região";
  renderCrop(item);
}

function render() {
  if (!state.page || !state.image) return;
  renderSummary();
  renderList();
  renderOverlay();
  renderInspector();
}

function setZoom(value, anchorX, anchorY) {
  if (!state.image) return;
  const viewport = $("viewport"), stage = $("image-stage");
  const old = state.zoom;
  const imgX = (viewport.scrollLeft + anchorX - stage.offsetLeft) / old;
  const imgY = (viewport.scrollTop + anchorY - stage.offsetTop) / old;
  state.zoom = Math.max(0.08, Math.min(4, value));
  stage.style.width = `${state.image.naturalWidth * state.zoom}px`;
  stage.style.height = `${state.image.naturalHeight * state.zoom}px`;
  $("zoom-label").textContent = `${Math.round(state.zoom * 100)}%`;
  viewport.scrollLeft = stage.offsetLeft + imgX * state.zoom - anchorX;
  viewport.scrollTop = stage.offsetTop + imgY * state.zoom - anchorY;
  renderOverlay();
  if (state.draftRegion) placeBox($("drawing-box"), state.draftRegion);
}

function fitWidth() {
  const viewport = $("viewport");
  setZoom((viewport.clientWidth - 42) / state.image.naturalWidth, 0, 0);
  viewport.scrollLeft = 0;
  viewport.scrollTop = 0;
}

function fitPage() {
  const viewport = $("viewport");
  setZoom(Math.min((viewport.clientWidth - 42) / state.image.naturalWidth, (viewport.clientHeight - 42) / state.image.naturalHeight), 0, 0);
  viewport.scrollLeft = 0;
  viewport.scrollTop = 0;
}

function focusStaff(item) {
  const viewport = $("viewport"), stage = $("image-stage");
  const gap = spacing(item), region = effective(item).region || reviewZone(item);
  const x = (region.left + region.right) / 2, y = (item.staff_region.top + item.staff_region.bottom) / 2;
  const z = Math.min(2.5, (viewport.clientWidth - 36) / (16 * gap), (viewport.clientHeight - 48) / (12 * gap));
  setZoom(z, viewport.clientWidth / 2, viewport.clientHeight / 2);
  viewport.scrollLeft = stage.offsetLeft + x * state.zoom - viewport.clientWidth / 2;
  viewport.scrollTop = stage.offsetTop + y * state.zoom - viewport.clientHeight / 2;
}

function selectStaff(staffId, focus = false) {
  const item = itemFor(staffId);
  if (!item) return;
  state.selected = staffId;
  state.drawMode = false;
  state.draftRegion = effective(item).region ? { ...effective(item).region } : null;
  $("image-stage").classList.remove("drawing");
  $("drawing-box").hidden = true;
  render();
  if (focus) focusStaff(item);
}

function pendingStep(direction) {
  const items = state.page.view.clefs;
  const start = items.findIndex((item) => item.staff_id === state.selected);
  for (let offset = 1; offset <= items.length; offset++) {
    const index = (start + direction * offset + items.length * 2) % items.length;
    if (isPending(items[index])) { selectStaff(items[index].staff_id, true); return; }
  }
  toast("Não há outra pendência de clave.");
}

function setDecision(decision) {
  state.decisions[state.selected] = decision;
  state.dirty = true;
  state.drawMode = false;
  $("image-stage").classList.remove("drawing");
  $("drawing-box").hidden = true;
  state.draftRegion = decision.region ? { ...decision.region } : null;
  render();
  toast("Correção aplicada localmente. Salve para mantê-la ao reabrir.");
}

function cancelDraw() {
  state.drawMode = false;
  state.drawStart = null;
  $("image-stage").classList.remove("drawing");
  $("drawing-box").hidden = true;
  renderInspector();
}

function imagePoint(event) {
  const rect = $("image-stage").getBoundingClientRect();
  return FluteGeometry.screenToImage(
    event.clientX, event.clientY, rect.left, rect.top, state.zoom,
    state.image.naturalWidth, state.image.naturalHeight,
  );
}

function drawPreview(a, b) {
  const region = { left: Math.min(a.x, b.x), top: Math.min(a.y, b.y), right: Math.max(a.x, b.x), bottom: Math.max(a.y, b.y) };
  placeBox($("drawing-box"), region);
  $("drawing-box").hidden = false;
  return region;
}

async function loadPage(pageId) {
  if (!state.pages.some((page) => page.id === pageId)) throw new Error("partitura fora do catálogo");
  if (state.dirty && !window.confirm("Descartar correções ainda não salvas?")) {
    $("page-select").value = state.page.id;
    return;
  }
  const page = await jsonRequest(`/api/pages/${pageId}`);
  const image = $("score-image");
  await new Promise((resolve, reject) => {
    image.onload = resolve;
    image.onerror = () => reject(new Error("imagem da partitura não pôde ser carregada"));
    image.src = `/api/pages/${pageId}/image`;
  });
  state.page = page;
  state.image = image;
  state.decisions = structuredClone(page.decisions);
  state.revision = page.revision;
  state.dirty = false;
  state.screen = "editor";
  $("home-screen").hidden = true;
  $("editor-shell").hidden = false;
  $("page-select").value = pageId;
  state.selected = null;
  state.draftRegion = null;
  const first = page.view.clefs.find(isPending) || page.view.clefs[0];
  if (first) selectStaff(first.staff_id, false);
  fitWidth();
  render();
}

async function save() {
  if (!state.dirty) return;
  try {
    const page = await jsonRequest(`/api/pages/${state.page.id}/corrections`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", "X-FluteOMR-Token": state.token },
      body: JSON.stringify({ base_revision: state.revision, decisions: state.decisions }),
    });
    state.page = page;
    state.decisions = structuredClone(page.decisions);
    state.revision = page.revision;
    state.dirty = false;
    render();
    toast("Correções salvas em arquivo separado.");
  } catch (error) { toast(`Não foi possível salvar: ${error.message}`); }
}

function bindActions() {
  $("back-home").addEventListener("click", () => showHome().catch((error) => toast(error.message)));
  $("page-select").addEventListener("change", (event) => loadPage(event.target.value).catch((error) => toast(error.message)));
  $("zoom-in").addEventListener("click", () => setZoom(state.zoom * 1.25, $("viewport").clientWidth / 2, $("viewport").clientHeight / 2));
  $("zoom-out").addEventListener("click", () => setZoom(state.zoom / 1.25, $("viewport").clientWidth / 2, $("viewport").clientHeight / 2));
  $("fit-width").addEventListener("click", fitWidth);
  $("fit-page").addEventListener("click", fitPage);
  $("overlay-toggle").addEventListener("click", () => {
    state.overlays = !state.overlays;
    $("overlay-toggle").setAttribute("aria-pressed", String(state.overlays));
    renderOverlay();
  });
  $("left-toggle").addEventListener("click", () => $("workspace").classList.toggle("hide-left"));
  $("right-toggle").addEventListener("click", () => $("workspace").classList.toggle("hide-right"));
  $("previous-pending").addEventListener("click", () => pendingStep(-1));
  $("next-pending").addEventListener("click", () => pendingStep(1));
  $("save").addEventListener("click", save);
  document.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => {
    state.filter = button.dataset.filter;
    document.querySelectorAll("[data-filter]").forEach((candidate) => candidate.classList.toggle("active", candidate === button));
    renderList();
  }));
  $("draw-region").addEventListener("click", () => {
    if (!state.selected) return;
    if (state.drawMode) { cancelDraw(); return; }
    state.drawMode = true;
    state.draftRegion = null;
    $("image-stage").classList.add("drawing");
    renderInspector();
    toast("Arraste uma caixa na partitura. Esc cancela.");
  });
  $("use-current").addEventListener("click", () => {
    const region = effective(itemFor(state.selected)).region;
    if (region) { state.draftRegion = { ...region }; renderInspector(); }
  });
  $("apply-correction").addEventListener("click", () => {
    if (!state.draftRegion) return;
    setDecision({ state: "present", kind: $("clef-kind").value, region: { ...state.draftRegion } });
  });
  $("mark-absent").addEventListener("click", () => {
    if (window.confirm("Confirmar que não há nenhuma clave nesta pauta? A ausência apenas de clave de sol não é suficiente.")) {
      setDecision({ state: "absent", kind: null, region: null });
    }
  });
  $("restore-auto").addEventListener("click", () => {
    if (!state.decisions[state.selected]) return;
    delete state.decisions[state.selected];
    state.dirty = true;
    selectStaff(state.selected);
    toast("Correção removida localmente. Salve para manter essa alteração.");
  });
  const stage = $("image-stage");
  stage.addEventListener("pointerdown", (event) => {
    if (!state.drawMode) return;
    event.preventDefault();
    state.drawStart = imagePoint(event);
    stage.setPointerCapture(event.pointerId);
    drawPreview(state.drawStart, state.drawStart);
  }, true);
  stage.addEventListener("pointermove", (event) => {
    if (state.drawStart) drawPreview(state.drawStart, imagePoint(event));
  });
  stage.addEventListener("pointerup", (event) => {
    if (!state.drawStart) return;
    const region = drawPreview(state.drawStart, imagePoint(event));
    state.drawStart = null;
    if (region.right - region.left < 2 || region.bottom - region.top < 2) {
      toast("Arraste uma caixa maior para marcar a clave.");
      cancelDraw();
      return;
    }
    state.draftRegion = region;
    cancelDraw();
    renderInspector();
  });
  $("viewport").addEventListener("wheel", (event) => {
    if (!event.ctrlKey || !state.image) return;
    event.preventDefault();
    const rect = $("viewport").getBoundingClientRect();
    setZoom(state.zoom * (event.deltaY < 0 ? 1.15 : 1 / 1.15), event.clientX - rect.left, event.clientY - rect.top);
  }, { passive: false });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.drawMode) cancelDraw();
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault(); save();
    }
  });
  window.addEventListener("beforeunload", (event) => {
    if (state.dirty) { event.preventDefault(); event.returnValue = ""; }
  });
}

async function start() {
  bindActions();
  try {
    await showHome();
    for (const page of state.pages) {
      const option = document.createElement("option");
      option.value = page.id;
      option.textContent = page.name;
      $("page-select").append(option);
    }
  } catch (error) {
    $("home-error").hidden = false;
    $("home-error").textContent = `Não foi possível carregar o catálogo: ${error.message}`;
    toast(error.message);
  }
}

start();
