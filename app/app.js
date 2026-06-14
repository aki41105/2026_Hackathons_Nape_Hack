const fileInput = document.querySelector("#fileInput");
const dropZone = document.querySelector("#dropZone");
const dropTitle = document.querySelector(".drop-title");
const dropMeta = document.querySelector(".drop-meta");
const queryPreview = document.querySelector("#queryPreview");
const statusPill = document.querySelector("#statusPill");
const sampleList = document.querySelector("#sampleList");
const sampleCount = document.querySelector("#sampleCount");
const resultEmpty = document.querySelector("#resultEmpty");
const recommendationGrid = document.querySelector("#recommendationGrid");
const recommendationTemplate = document.querySelector("#recommendationTemplate");
const clearButton = document.querySelector("#clearButton");
const searchMoodMap = document.querySelector("#searchMoodMap");
const searchMoodMessage = document.querySelector("#searchMoodMessage");
const searchRegisterForm = document.querySelector("#searchRegisterForm");
const searchMusicUrlInput = document.querySelector("#searchMusicUrlInput");
const searchRegisterButton = document.querySelector("#searchRegisterButton");
const searchRegisterMessage = document.querySelector("#searchRegisterMessage");
const registerForm = document.querySelector("#registerForm");
const registerFileInput = document.querySelector("#registerFileInput");
const musicUrlInput = document.querySelector("#musicUrlInput");
const registerButton = document.querySelector("#registerButton");
const registerMessage = document.querySelector("#registerMessage");
const refreshLibraryButton = document.querySelector("#refreshLibraryButton");
const libraryCount = document.querySelector("#libraryCount");
const libraryGrid = document.querySelector("#libraryGrid");
const libraryTemplate = document.querySelector("#libraryTemplate");
const tabButtons = document.querySelectorAll(".tab-button");
const tabPanels = document.querySelectorAll(".tab-panel");
const refreshAnnotationButton = document.querySelector("#refreshAnnotationButton");
const annotationCount = document.querySelector("#annotationCount");
const annotationGrid = document.querySelector("#annotationGrid");
const annotationTemplate = document.querySelector("#annotationTemplate");
const emotionFilter = document.querySelector("#emotionFilter");
const stageImage = document.querySelector("#stageImage");
const stageId = document.querySelector("#stageId");
const stageMusicLink = document.querySelector("#stageMusicLink");
const stageEmotionButtons = document.querySelector("#stageEmotionButtons");
const stageStatus = document.querySelector("#stageStatus");
const stageImageButton = document.querySelector("#stageImageButton");
const prevAnnotationButton = document.querySelector("#prevAnnotationButton");
const nextAnnotationButton = document.querySelector("#nextAnnotationButton");
const imageDialog = document.querySelector("#imageDialog");
const dialogImage = document.querySelector("#dialogImage");
const dialogCloseButton = document.querySelector("#dialogCloseButton");

const sessionId = getSessionId();
let currentEventId = null;
let annotationItems = [];
let annotationOptions = [
  { key: "sentimental", label: "しみじみ", feeling: -1, energy: 1 },
  { key: "excited", label: "わくわく", feeling: 1, energy: 1 },
  { key: "nostalgic", label: "懐かしい", feeling: -1, energy: -1 },
  { key: "relaxed", label: "のんびり", feeling: 1, energy: -1 },
];
let currentEmotionFilter = "all";
let currentAnnotationIndex = 0;
let currentQueryFile = null;
let currentSearchMoodPoint = null;
let currentQueryObjectUrl = null;
const moodPlotBounds = {
  left: 424 / 1863,
  top: 202 / 1367,
  right: 1544 / 1863,
  bottom: 1020 / 1367,
};
const moodPlotEdgePadding = 0.004;

function optionForLabel(label) {
  return annotationOptions.find((option) => option.label === label);
}

function optionForKey(key) {
  return annotationOptions.find((option) => option.key === key);
}

function optionForPoint(feelingScore, energyScore) {
  if (feelingScore >= 0 && energyScore >= 0) return optionForKey("excited");
  if (feelingScore >= 0 && energyScore < 0) return optionForKey("relaxed");
  if (feelingScore < 0 && energyScore < 0) return optionForKey("nostalgic");
  return optionForKey("sentimental");
}

function scoreForOption(option) {
  return {
    feeling_score: option.feeling * 3,
    energy_score: option.energy * 3,
  };
}

function hasMoodPoint(item) {
  return item.feeling_score != null && item.energy_score != null;
}

function normalizeAnnotationItem(item) {
  if (!item.emotion_key && item.emotion_label) {
    const option = optionForLabel(item.emotion_label);
    if (option) item.emotion_key = option.key;
  }
  if (item.emotion_key && (item.feeling_score == null || item.energy_score == null)) {
    const option = optionForKey(item.emotion_key);
    if (option) Object.assign(item, scoreForOption(option));
  }
  return item;
}

const slotLabels = {
  nearest: "いちばん近いソラ",
  mood: "次に近いソラ",
  emotion_match: "気分も近いソラ",
  discovery: "寄り道のソラ",
  emotion_opposite: "いちばん遠いソラ",
};

const statusText = {
  ready: "選択前",
  selected: "写真選択済み",
  reading: "読んでいます",
  loading: "読んでいます",
  done: "",
  error: "エラー",
};

const featureLabels = {
  brightness_mean: "明るさ",
  saturation_mean: "鮮やかさ",
  warm_ratio: "暖色感",
  blue_ratio: "青さ",
  gray_ratio: "グレー感",
  dark_ratio: "暗さ",
  contrast: "明暗差",
  edge_density: "粗さ",
  sky_blue: "ソラの青さ",
  sky_cloud: "雲量",
  sky_gray: "曇り感",
  sky_warm: "夕方感",
  sky_texture: "雲の細かさ",
  sky_clear: "抜け感",
};

const barColors = {
  brightness_mean: "#f0b640",
  saturation_mean: "#8057df",
  warm_ratio: "#e8692c",
  blue_ratio: "#2f8fd8",
  gray_ratio: "#94a2a8",
  dark_ratio: "#263238",
  contrast: "#1f7a8c",
  edge_density: "#6f8753",
  sky_blue: "#2f8fd8",
  sky_cloud: "#8da3b3",
  sky_gray: "#94a2a8",
  sky_warm: "#e8692c",
  sky_texture: "#6b59c9",
  sky_clear: "#25a7d9",
};

init();

function init() {
  fetchTestImages();
  fetchLibrary();
  renderSearchMoodMap();

  fileInput.addEventListener("click", () => {
    fileInput.value = "";
  });

  fileInput.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (file) {
      setQueryFile(file);
    }
  });

  dropZone.addEventListener("dragover", (event) => {
    event.preventDefault();
    dropZone.classList.add("is-dragging");
  });

  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("is-dragging");
  });

  dropZone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropZone.classList.remove("is-dragging");
    const file = [...event.dataTransfer.files].find((item) => item.type.startsWith("image/"));
    if (file) {
      fileInput.files = event.dataTransfer.files;
      setQueryFile(file);
    }
  });

  clearButton.addEventListener("click", resetView);
  searchRegisterForm.addEventListener("submit", registerSearchPair);
  refreshLibraryButton.addEventListener("click", fetchLibrary);
  refreshAnnotationButton?.addEventListener("click", fetchAnnotations);
  stageImageButton?.addEventListener("click", () => openImageDialog(stageImage.src));
  dialogCloseButton.addEventListener("click", () => imageDialog.close());
  imageDialog.addEventListener("click", (event) => {
    if (event.target === imageDialog) imageDialog.close();
  });
  prevAnnotationButton?.addEventListener("click", () => moveAnnotation(-1));
  nextAnnotationButton?.addEventListener("click", () => moveAnnotation(1));
  registerForm.addEventListener("submit", registerPair);
  registerFileInput.addEventListener("change", updateRegisterFileLabel);
  for (const button of tabButtons) {
    button.addEventListener("click", () => switchTab(button.dataset.tab));
  }
}

function refreshQueryPreview(file) {
  currentQueryFile = file;
  if (currentQueryObjectUrl) URL.revokeObjectURL(currentQueryObjectUrl);
  const objectUrl = URL.createObjectURL(file);
  currentQueryObjectUrl = objectUrl;
  queryPreview.src = objectUrl;
  dropZone.style.backgroundImage = `linear-gradient(rgba(248, 239, 226, 0.46), rgba(248, 239, 226, 0.76)), url("${objectUrl}")`;
  dropZone.classList.add("has-file");
}

function setQueryFile(file) {
  currentQueryFile = file;
  currentSearchMoodPoint = null;
  if (currentQueryObjectUrl) URL.revokeObjectURL(currentQueryObjectUrl);
  const objectUrl = URL.createObjectURL(file);
  currentQueryObjectUrl = objectUrl;
  queryPreview.src = objectUrl;
  dropZone.style.backgroundImage = `linear-gradient(rgba(248, 239, 226, 0.46), rgba(248, 239, 226, 0.76)), url("${objectUrl}")`;
  renderSearchMoodMap();
  dropZone.classList.add("has-file");
  dropTitle.textContent = "写真を選択しました";
  dropMeta.textContent = "感情ラベルを入力すると検索します";
  currentEventId = null;
  recommendationGrid.innerHTML = "";
  setSearchRegisterVisible(false);
  resultEmpty.classList.remove("is-hidden");
  setStatus("selected", "is-busy");
  searchMoodMessage.textContent = "写真を変更しました。図の上で気分に近い位置を押すと検索します。";
  resultEmpty.innerHTML = "<p>感情ラベルを入力すると、ここに3曲が届きます。</p>";
}

function maybeRecommendFromCurrentInput() {
  if (!currentQueryFile || !currentSearchMoodPoint) return;
  recommendFromFile(currentQueryFile);
}

function switchTab(name) {
  for (const button of tabButtons) {
    const active = button.dataset.tab === name;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  }

  for (const panel of tabPanels) {
    const active = panel.dataset.panel === name;
    panel.classList.toggle("is-active", active);
    panel.hidden = !active;
  }

  if (name === "library") {
    fetchLibrary();
  } else if (name === "annotation") {
    fetchAnnotations();
  }
}

async function fetchTestImages() {
  try {
    const response = await fetch("/api/test-images");
    if (!response.ok) throw new Error("test image list failed");
    const data = await response.json();
    const items = data.items || [];
    sampleCount.textContent = `${items.length}`;
    sampleList.replaceChildren(...items.slice(0, 10).map(makeSampleButton));
  } catch (error) {
    console.error(error);
    sampleCount.textContent = "0";
    sampleList.innerHTML = "";
  }
}

async function recommendFromFile(file) {
  currentQueryFile = file;
  if (!currentSearchMoodPoint) {
    setQueryFile(file);
    return;
  }
  refreshQueryPreview(file);
  setStatus("reading", "is-busy");
  currentEventId = null;
  recommendationGrid.innerHTML = "";
  setSearchRegisterVisible(false);
  resultEmpty.classList.remove("is-hidden");
  resultEmpty.innerHTML = `
    <div class="loading-copy">
      <p>ソラの気配を読んでいます</p>
      <span>似たソラの記憶を探しています</span>
    </div>
  `;

  const formData = new FormData();
  formData.append("file", file);
  formData.append("session_id", sessionId);
  formData.append("feeling_score", String(currentSearchMoodPoint.feeling_score));
  formData.append("energy_score", String(currentSearchMoodPoint.energy_score));

  try {
    const response = await fetch("/api/recommend", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || "recommend failed");
    }
    const data = await response.json();
    currentEventId = data.event_id;
    renderRecommendations(data.recommendations || []);
    setStatus("done", "is-ok");
  } catch (error) {
    console.error(error);
    setStatus("error", "is-error");
    setSearchRegisterVisible(false);
    resultEmpty.classList.remove("is-hidden");
    resultEmpty.innerHTML = "<p>画像を処理できませんでした。</p>";
  }
}

function makeSampleButton(item) {
  const button = document.createElement("button");
  button.className = "sample-button";
  button.type = "button";
  button.title = "サンプルのソラで試す";

  const image = document.createElement("img");
  image.src = item.url;
  image.alt = "";

  button.append(image);
  button.addEventListener("click", () => recommendFromSample(item));
  return button;
}

async function recommendFromSample(item) {
  setStatus("loading", "is-busy");
  try {
    const response = await fetch(item.url);
    if (!response.ok) throw new Error("sample image fetch failed");
    const blob = await response.blob();
    const file = new File([blob], item.name, { type: blob.type || "image/jpeg" });
    await recommendFromFile(file);
  } catch (error) {
    console.error(error);
    setStatus("error", "is-error");
  }
}

async function registerPair(event) {
  event.preventDefault();
  const file = registerFileInput.files?.[0];
  const url = musicUrlInput.value.trim();
  if (!file || !url) return;
  if (!isYouTubeMusicUrl(url)) {
    registerMessage.textContent = "YouTube Musicのリンクを入力してください";
    registerMessage.className = "form-message is-error";
    return;
  }

  registerButton.disabled = true;
  registerMessage.textContent = "登録しています";
  registerMessage.className = "form-message";

  const formData = new FormData();
  formData.append("file", file);
  formData.append("youtube_music_url", url);

  try {
    const response = await fetch("/api/register", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || "register failed");
    }
    registerForm.reset();
    updateRegisterFileLabel();
    registerMessage.textContent = "登録しました";
    registerMessage.classList.add("is-success");
    await fetchLibrary();
  } catch (error) {
    console.error(error);
    registerMessage.textContent = "登録できませんでした";
    registerMessage.classList.add("is-error");
  } finally {
    registerButton.disabled = false;
  }
}

async function registerSearchPair(event) {
  event.preventDefault();
  const url = searchMusicUrlInput.value.trim();
  if (!currentQueryFile || !currentSearchMoodPoint || !url) {
    searchRegisterMessage.textContent = "写真、感情ラベル、YouTube Musicリンクが必要です";
    searchRegisterMessage.className = "form-message is-error";
    return;
  }
  if (!isYouTubeMusicUrl(url)) {
    searchRegisterMessage.textContent = "YouTube Musicのリンクを入力してください";
    searchRegisterMessage.className = "form-message is-error";
    return;
  }

  searchRegisterButton.disabled = true;
  searchRegisterMessage.textContent = "保存しています";
  searchRegisterMessage.className = "form-message";

  const formData = new FormData();
  formData.append("file", currentQueryFile);
  formData.append("youtube_music_url", url);
  formData.append("feeling_score", String(currentSearchMoodPoint.feeling_score));
  formData.append("energy_score", String(currentSearchMoodPoint.energy_score));

  try {
    const response = await fetch("/api/register", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || "register failed");
    }
    searchMusicUrlInput.value = "";
    searchRegisterMessage.textContent = "保存しました";
    searchRegisterMessage.classList.add("is-success");
    await fetchLibrary();
  } catch (error) {
    console.error(error);
    searchRegisterMessage.textContent = "保存できませんでした";
    searchRegisterMessage.classList.add("is-error");
  } finally {
    searchRegisterButton.disabled = false;
  }
}

function isYouTubeMusicUrl(value) {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/^www\./, "");
    return host === "music.youtube.com" && Boolean(url.searchParams.get("v"));
  } catch {
    return false;
  }
}

async function fetchLibrary() {
  libraryGrid.innerHTML = "";
  libraryCount.textContent = "--";
  try {
    const response = await fetch("/api/library?limit=120");
    if (!response.ok) throw new Error("library fetch failed");
    const data = await response.json();
    const items = data.items || [];
    libraryCount.textContent = `${data.count || items.length}`;
    libraryGrid.replaceChildren(...items.map(makeLibraryCard));
  } catch (error) {
    console.error(error);
    libraryCount.textContent = "0";
    libraryGrid.innerHTML = '<p class="library-empty">読み込めませんでした。</p>';
  }
}

async function fetchAnnotations() {
  annotationGrid.innerHTML = "";
  annotationCount.textContent = "--";
  try {
    const response = await fetch("/api/annotations?limit=300");
    if (!response.ok) throw new Error("annotation fetch failed");
    const data = await response.json();
    annotationOptions = data.emotion_options || annotationOptions;
    annotationItems = (data.items || []).map(normalizeAnnotationItem);
    currentAnnotationIndex = firstUnlabeledIndex();
    renderEmotionFilter();
    renderAnnotationStage();
    renderAnnotations();
  } catch (error) {
    console.error(error);
    annotationCount.textContent = "0";
    annotationGrid.innerHTML = '<p class="library-empty">読み込めませんでした。</p>';
  }
}

function renderEmotionFilter() {
  const options = [
    { value: "all", label: "すべて" },
    { value: "none", label: "未設定" },
    ...annotationOptions.map((option) => ({ value: option.key, label: option.label })),
  ];
  emotionFilter.replaceChildren(
    ...options.map((option) => {
      const button = document.createElement("button");
      button.className = "filter-button";
      button.type = "button";
      button.textContent = option.label;
      button.classList.toggle("is-active", currentEmotionFilter === option.value);
      button.addEventListener("click", () => {
        currentEmotionFilter = option.value;
        renderEmotionFilter();
        renderAnnotations();
      });
      return button;
    }),
  );
}

function renderAnnotations() {
  const items = annotationItems.filter((item) => {
    if (currentEmotionFilter === "all") return true;
    if (currentEmotionFilter === "none") return !hasMoodPoint(item);
    return item.emotion_key === currentEmotionFilter;
  });
  annotationCount.textContent = `${items.length} / ${annotationItems.length}`;
  annotationGrid.replaceChildren(...items.map(makeAnnotationCard));
}

function renderAnnotationStage() {
  if (annotationItems.length === 0) {
    stageImage.removeAttribute("src");
    stageId.textContent = "--";
    stageMusicLink.removeAttribute("href");
    stageEmotionButtons.innerHTML = "";
    stageStatus.textContent = "表示できる写真がありません";
    return;
  }

  currentAnnotationIndex = clampIndex(currentAnnotationIndex);
  const item = annotationItems[currentAnnotationIndex];
  stageImage.src = item.image_url;
  stageImageButton.dataset.photoId = item.photo_id;
  stageId.textContent = `#${String(item.photo_id).padStart(3, "0")}`;
  stageMusicLink.href = item.youtube_music_url;
  renderMoodMap(item);
  stageStatus.textContent = hasMoodPoint(item) ? "保存済み" : "未設定";
  prevAnnotationButton.disabled = annotationItems.length <= 1;
  nextAnnotationButton.disabled = annotationItems.length <= 1;
}

function renderMoodMap(item) {
  stageEmotionButtons.classList.add("mood-map");
  stageEmotionButtons.setAttribute("role", "button");
  stageEmotionButtons.setAttribute("tabindex", "0");
  stageEmotionButtons.setAttribute("aria-label", "ムードメーター上の位置を選択");

  const image = document.createElement("img");
  image.className = "mood-map-image";
  image.src = "/static/mood_meter.png?v=20260614-0015";
  image.alt = "ムードメーター";
  stageEmotionButtons.replaceChildren(image);

  if (item.feeling_score != null && item.energy_score != null) {
    const marker = document.createElement("span");
    marker.className = "mood-marker";
    const position = markerPosition(item.feeling_score, item.energy_score);
    marker.style.left = `${position.left}%`;
    marker.style.top = `${position.top}%`;
    stageEmotionButtons.append(marker);
  }

  stageEmotionButtons.onpointerdown = (event) => {
    event.preventDefault();
    const point = pointFromMoodEvent(event);
    if (!point) return;
    setEmotionPoint(item, point, false);
  };
  stageEmotionButtons.onkeydown = (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    const point = {
      feeling_score: item.feeling_score ?? 0,
      energy_score: item.energy_score ?? 0,
    };
    setEmotionPoint(item, point, false);
  };
}

function renderSearchMoodMap() {
  if (!searchMoodMap) return;
  searchMoodMap.classList.add("mood-map");
  searchMoodMap.setAttribute("role", "button");
  searchMoodMap.setAttribute("tabindex", "0");
  searchMoodMap.setAttribute("aria-label", "任意の感情位置を選択");

  const image = document.createElement("img");
  image.className = "mood-map-image";
  image.src = "/static/mood_meter.png?v=20260614-0015";
  image.alt = "ムードメーター";
  searchMoodMap.replaceChildren(image);

  if (currentSearchMoodPoint) {
    const marker = document.createElement("span");
    marker.className = "mood-marker";
    const position = markerPosition(currentSearchMoodPoint.feeling_score, currentSearchMoodPoint.energy_score);
    marker.style.left = `${position.left}%`;
    marker.style.top = `${position.top}%`;
    searchMoodMap.append(marker);
  }

  searchMoodMap.onpointerdown = (event) => {
    event.preventDefault();
    const point = pointFromMoodEvent(event, searchMoodMap);
    if (!point) {
      searchMoodMessage.textContent = "色のついたゾーンの中を押してください。";
      return;
    }
    currentSearchMoodPoint = point;
    searchMoodMessage.textContent = "";
    renderSearchMoodMap();
    maybeRecommendFromCurrentInput();
  };
  searchMoodMap.onkeydown = (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    currentSearchMoodPoint = currentSearchMoodPoint || { feeling_score: 0, energy_score: 0 };
    searchMoodMessage.textContent = "";
    renderSearchMoodMap();
    maybeRecommendFromCurrentInput();
  };
}

function markerPosition(feelingScore, energyScore) {
  const x = (Number(feelingScore) + 5) / 10;
  const y = (5 - Number(energyScore)) / 10;
  return {
    left: (moodPlotBounds.left + x * (moodPlotBounds.right - moodPlotBounds.left)) * 100,
    top: (moodPlotBounds.top + y * (moodPlotBounds.bottom - moodPlotBounds.top)) * 100,
  };
}

function pointFromMoodEvent(event, target = stageEmotionButtons) {
  const rect = target.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return null;
  const rawX = (event.clientX - rect.left) / rect.width;
  const rawY = (event.clientY - rect.top) / rect.height;
  if (!isPointInsideMoodPlot(rawX, rawY)) return null;
  const x = rawX;
  const y = rawY;
  const plotX = (x - moodPlotBounds.left) / (moodPlotBounds.right - moodPlotBounds.left);
  const plotY = (y - moodPlotBounds.top) / (moodPlotBounds.bottom - moodPlotBounds.top);
  return {
    feeling_score: Number((plotX * 10 - 5).toFixed(2)),
    energy_score: Number((5 - plotY * 10).toFixed(2)),
  };
}

function isPointInsideMoodPlot(x, y) {
  return (
    x >= moodPlotBounds.left + moodPlotEdgePadding &&
    x <= moodPlotBounds.right - moodPlotEdgePadding &&
    y >= moodPlotBounds.top + moodPlotEdgePadding &&
    y <= moodPlotBounds.bottom - moodPlotEdgePadding
  );
}

function moveAnnotation(step) {
  if (annotationItems.length === 0) return;
  currentAnnotationIndex = (currentAnnotationIndex + step + annotationItems.length) % annotationItems.length;
  renderAnnotationStage();
}

function firstUnlabeledIndex() {
  const index = annotationItems.findIndex((item) => !hasMoodPoint(item));
  return index >= 0 ? index : 0;
}

function nextUnlabeledIndex(afterIndex) {
  if (annotationItems.length === 0) return 0;
  for (let offset = 1; offset <= annotationItems.length; offset += 1) {
    const index = (afterIndex + offset) % annotationItems.length;
    if (!hasMoodPoint(annotationItems[index])) return index;
  }
  return afterIndex;
}

function clampIndex(index) {
  if (annotationItems.length === 0) return 0;
  return Math.max(0, Math.min(annotationItems.length - 1, index));
}

function makeAnnotationCard(item) {
  const node = annotationTemplate.content.firstElementChild.cloneNode(true);
  node.dataset.photoId = item.photo_id;
  node.classList.toggle("is-selected", annotationItems[currentAnnotationIndex]?.photo_id === item.photo_id);

  const image = node.querySelector(".annotation-image");
  image.src = item.image_url;
  node.querySelector(".annotation-image-button").addEventListener("click", () => selectAnnotationItem(item.photo_id));

  node.querySelector(".annotation-id").textContent = `#${String(item.photo_id).padStart(3, "0")}`;

  const link = node.querySelector(".annotation-link");
  link.href = item.youtube_music_url;

  node.querySelector(".emotion-buttons")?.remove();

  const status = node.querySelector(".annotation-status");
  status.textContent = hasMoodPoint(item) ? "保存済み" : "未設定";
  return node;
}

function openImageDialog(src) {
  if (!src) return;
  dialogImage.src = src;
  if (typeof imageDialog.showModal === "function") {
    imageDialog.showModal();
  }
}

function selectAnnotationItem(photoId) {
  const index = annotationItems.findIndex((item) => item.photo_id === photoId);
  if (index < 0) return;
  currentAnnotationIndex = index;
  renderAnnotationStage();
  renderAnnotations();
  document.querySelector(".annotation-stage")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function setEmotionPoint(item, point, advanceAfterSave = false) {
  stageEmotionButtons.classList.add("is-saving");
  try {
    const response = await fetch(`/api/photos/${item.photo_id}/emotion`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        feeling_score: point.feeling_score,
        energy_score: point.energy_score,
      }),
    });
    if (!response.ok) throw new Error("emotion update failed");
    const saved = await response.json();
    item.emotion_key = saved.emotion_key || "";
    item.emotion_label = saved.emotion_label || "";
    item.feeling_score = saved.feeling_score ?? point.feeling_score;
    item.energy_score = saved.energy_score ?? point.energy_score;
    stageStatus.textContent = "保存しました";
    renderAnnotations();
    if (advanceAfterSave) {
      currentAnnotationIndex = nextUnlabeledIndex(currentAnnotationIndex);
      setTimeout(renderAnnotationStage, 220);
    } else {
      renderAnnotationStage();
    }
  } catch (error) {
    console.error(error);
    stageStatus.textContent = "保存できませんでした";
  } finally {
    stageEmotionButtons.classList.remove("is-saving");
  }
}

function makeLibraryCard(item) {
  const node = libraryTemplate.content.firstElementChild.cloneNode(true);
  const image = node.querySelector(".library-image");
  image.src = item.image_url;

  node.querySelector(".library-id").textContent = `#${String(item.photo_id).padStart(3, "0")}`;

  const link = node.querySelector(".library-link");
  link.href = item.youtube_music_url;
  return node;
}

function updateRegisterFileLabel() {
  const label = document.querySelector(".register-photo span");
  const file = registerFileInput.files?.[0];
  label.textContent = file ? "選択済み" : "写真を選ぶ";
}

function renderRecommendations(items) {
  recommendationGrid.innerHTML = "";
  if (items.length === 0) {
    setSearchRegisterVisible(false);
    resultEmpty.classList.remove("is-hidden");
    resultEmpty.innerHTML = "<p>推薦できる登録写真がありません。</p>";
    return;
  }

  resultEmpty.classList.add("is-hidden");
  for (const item of items) {
    recommendationGrid.append(makeRecommendationCard(item));
  }
  setSearchRegisterVisible(true);
}

function setSearchRegisterVisible(visible) {
  searchRegisterForm.classList.toggle("is-hidden", !visible);
  if (!visible) {
    searchMusicUrlInput.value = "";
    searchRegisterMessage.textContent = "";
  }
}

function makeRecommendationCard(item) {
  const node = recommendationTemplate.content.firstElementChild.cloneNode(true);
  const image = node.querySelector(".match-image");
  image.src = item.image_url;

  node.querySelector(".slot-label").textContent = slotLabels[item.slot] || item.slot;

  const link = node.querySelector(".primary-link");
  link.href = item.youtube_music_url;
  link.addEventListener("click", () => sendFeedback(item, "clicked", 1));

  let feedbackState = null;
  const feedbackButtons = [...node.querySelectorAll(".ghost-button")];
  const feedbackLabels = {
    liked: "よかった",
    disliked: "違う",
  };

  function renderFeedbackButtons() {
    for (const button of feedbackButtons) {
      const action = button.dataset.action;
      button.disabled = false;
      button.classList.toggle("is-selected", feedbackState === action);
      button.textContent = feedbackLabels[action] || button.textContent;
      button.setAttribute("aria-pressed", String(feedbackState === action));
    }
  }

  for (const button of feedbackButtons) {
    if (button.dataset.action === "liked") button.classList.add("good-button");
    button.addEventListener("click", async () => {
      const action = button.dataset.action;
      if (feedbackState === action) return;
      const nextValue = action === "liked" ? 1 : -1;
      for (const target of feedbackButtons) target.disabled = true;
      await sendFeedback(item, action, nextValue);
      feedbackState = action;
      renderFeedbackButtons();
    });
  }
  renderFeedbackButtons();

  return node;
}

function makeFeatureRow(key, value) {
  const row = document.createElement("div");
  row.className = "feature-row";

  const label = document.createElement("span");
  label.textContent = featureLabels[key] || key;

  const track = document.createElement("span");
  track.className = "bar-track";
  const fill = document.createElement("span");
  fill.className = "bar-fill";
  fill.style.width = `${Math.max(0, Math.min(1, value)) * 100}%`;
  fill.style.background = barColors[key] || "#1f7a8c";
  track.append(fill);

  const number = document.createElement("small");
  number.textContent = formatRatio(value);

  row.append(label, track, number);
  return row;
}

async function sendFeedback(item, action, value) {
  if (!item.photo_id) return;
  try {
    await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_id: currentEventId,
        photo_id: item.photo_id,
        action,
        value,
        session_id: sessionId,
      }),
    });
  } catch (error) {
    console.error(error);
  }
}

function resetView() {
  currentEventId = null;
  currentQueryFile = null;
  currentSearchMoodPoint = null;
  if (currentQueryObjectUrl) {
    URL.revokeObjectURL(currentQueryObjectUrl);
    currentQueryObjectUrl = null;
  }
  fileInput.value = "";
  dropZone.classList.remove("has-file");
  dropZone.style.backgroundImage = "";
  dropTitle.textContent = "ソラの写真をアップロード";
  dropMeta.textContent = "JPG / PNG / WEBP";
  queryPreview.removeAttribute("src");
  recommendationGrid.innerHTML = "";
  setSearchRegisterVisible(false);
  resultEmpty.classList.remove("is-hidden");
  resultEmpty.innerHTML = "<p>写真と感情ラベルを入力すると、ここに3曲が届きます。</p>";
  searchMoodMessage.textContent = "写真を選んでから、図の上で気分に近い位置を押してください。";
  renderSearchMoodMap();
  setStatus("ready");
}

function setStatus(label, modifier) {
  statusPill.hidden = label === "done";
  statusPill.className = "status-pill";
  if (modifier) statusPill.classList.add(modifier);
  statusPill.textContent = statusText[label] || label;
}

function getSessionId() {
  const key = "cloud-tune-session";
  const existing = localStorage.getItem(key);
  if (existing) return existing;
  const created = crypto.randomUUID?.() || `session-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  localStorage.setItem(key, created);
  return created;
}

function clamp01(value) {
  const number = Number(value || 0);
  return Math.max(0, Math.min(1, number));
}

function formatRatio(value) {
  return Number(value || 0).toFixed(2);
}
