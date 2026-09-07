/* BT Speaker Remote — iOS-ish client (Hebrew RTL) */

const $ = (sel) => document.querySelector(sel);

const STRINGS = {
  btOff: "כבוי",
  btOn: "פועל",
  btConnectedTo: (names) => `מחובר ל־${names}`,
  noSpeaker: "אין רמקול מחובר",
  tapScan: "לחץ סריקה כדי למצוא רמקולים",
  noDevices: "לא נמצאו מכשירים",
  scanAgain: "סרוק שוב כשהרמקול דולק",
  audio: "אודיו",
  device: "מכשיר",
  paired: "מזווג",
  connect: "התחבר",
  pair: "זיווג",
  disconnect: "נתק",
  forget: "שכח",
  nothingPlaying: "כלום לא מתנגן",
  playing: "מתנגן…",
  paused: "מושהה",
  pasteHint: "הדבק קישור יוטיוב / פלייליסט / מיקס",
  linkCopied: "הקישור הועתק",
  copyFailed: "העתקה נכשלה — העתק ידנית",
  noLink: "אין קישור להעתקה",
  authPrompt: "אין הרשאה. הדבק קישור הזמנה (או טוקן) שנוצר עם add_device.sh:",
  authFailed: "אימות נכשל",
  inviteInvalid: "הזמנה לא תקפה",
  deviceRegistered: (n) => `מכשיר נרשם: ${n}`,
  signedIn: (n) => `מחובר: ${n}`,
  signedInAsAdmin: (n) => `מחובר כ־${n} (מנהל)`,
  signedInAs: (n) => `מחובר כ־${n}`,
  enterDeviceName: "הזן שם מכשיר קודם",
  creatingInvite: "יוצר הזמנה…",
  inviteReady: (n) => `הזמנה מוכנה ל־${n}`,
  inviteCreated: (n) => `הזמנה נוצרה: ${n}`,
  failed: "נכשל",
  revokeConfirm: (n) => `לבטל גישה ל־"${n}"?`,
  revokeFailed: "ביטול גישה נכשל",
  revoked: "הגישה בוטלה",
  deleteConfirm: (n) => `למחוק את "${n}" מהרשימה?`,
  deleteFailed: "מחיקה נכשלה",
  deleted: "נמחק",
  cancelFailed: "ביטול נכשל",
  inviteCancelled: "ההזמנה בוטלה",
  noOpenInvites: "אין הזמנות פתוחות",
  none: "אין",
  expires: (when) => `פג תוקף ${when}`,
  lastSeen: (when) => `נראה לאחרונה ${when}`,
  you: " · אתה",
  admin: " · מנהל",
  revokedTag: " · בוטל",
  copy: "העתק",
  cancel: "בטל",
  revoke: "בטל גישה",
  delete: "מחק",
  authRequired: "נדרשת הרשאה — הזן טוקן",
  cannotReach: "לא ניתן להגיע לשרת",
  turningBtOn: "מדליק בלוטות׳…",
  turningBtOff: "מכבה בלוטות׳…",
  btOnStatus: "בלוטות׳ פועל",
  btOffStatus: "בלוטות׳ כבוי",
  powerFailed: "החלפת בלוטות׳ נכשלה",
  scanning: "סורק רמקולים…",
  scanningStatus: "סורק…",
  foundDevices: (n) => `נמצאו ${n} מכשירים`,
  scanFailed: "סריקה נכשלה",
  connecting: (n) => `מתחבר ל־${n}…`,
  connectedTo: (n) => `מחובר ל־${n}`,
  connectFailed: "החיבור נכשל",
  disconnecting: "מתנתק…",
  disconnected: "נותק",
  disconnectFailed: "ניתוק נכשל",
  forgetConfirm: (n) => `לשכוח את "${n}"?`,
  forgetting: "שוכח מכשיר…",
  deviceForgotten: "המכשיר נשכח",
  forgetFailed: "שכחה נכשלה",
  pasteUrlFirst: "הדבק קישור יוטיוב קודם",
  startingStream: "מוריד מיוטיוב ואז מנגן…",
  startingPlayback: "מוריד מיוטיוב…",
  playingTitle: (t) => `מתנגן: ${t}`,
  playingStatus: "מתנגן",
  loadingTrack: "טוען…",
  playFailed: "ניגון נכשל",
  noBtSpeaker: "אין רמקול בלוטות׳ מחובר — חבר רמקול כדי לנגן",
  stopped: "נעצר",
  stopFailed: "עצירה נכשלה",
  pauseFailed: "השהיה נכשלה",
  resumeFailed: "המשך נכשל",
  ready: "מוכן",
  searching: "מחפש…",
  searchFailed: "חיפוש נכשל",
  noResults: "אין תוצאות",
  enterSearch: "הזן מילות חיפוש",
  seekFailed: "דילוג נכשל",
  nextFailed: "מעבר לבא נכשל",
  prevFailed: "מעבר לקודם נכשל",
  playlistPos: (cur, total) => `רצועה ${cur} מתוך ${total}`,
  queueHint: "לחץ לרשימה — אפשר לקפוץ לשיר",
  addToQueue: "הוסף לתור",
  queued: (t) => t ? `נוסף לתור: ${t}` : "נוסף לתור",
  queueFailed: "הוספה לתור נכשלה",
  saveToLibrary: "שמור לספרייה",
  working: "עובד…",
  busyTimeout: "הפעולה ארכה מדי — מסתיר את המסך. אפשר לרענן אם משהו נתקע",
  requestTimeout: "השרת לא ענה בזמן",
  noFiles: "אין קבצים עדיין",
  dropHint: "העלה מהטלפון או זרוק קבצים לתיקיית media במחשב",
  noPlaylists: "אין פלייליסטים",
  noHistory: "אין האזנות אחרונות",
  upload: "העלה",
  uploading: "מעלה…",
  uploaded: "הועלה",
  uploadFailed: "העלאה נכשלה",
  deleteFileConfirm: (n) => `למחוק את "${n}"?`,
  savingUrl: "שומר לספרייה ברקע…",
  saveStarted: "שומר ברקע — תופיע בספרייה כשיסתיים",
  saveFailed: "שמירה לספרייה נכשלה",
  saveDone: (t) => t ? `נשמר: ${t}` : "נשמר לספרייה",
  pasteUrlToSave: "הדבק קישור לשמירה",
  enterPlaylistName: "הזן שם לפלייליסט",
  playlistCreated: (n) => `נוצר: ${n}`,
  playlistEmpty: "הפלייליסט ריק",
  addToPlaylist: "הוסף לפלייליסט",
  addedToPlaylist: "נוסף לפלייליסט",
  createPlaylistFirst: "צור פלייליסט קודם",
  playingPlaylist: (n) => `מנגן: ${n}`,
  recNeedHttps: "הקלטה מהמיקרופון דורשת HTTPS. אפשר להעלות קובץ קולי.",
  recDenied: "אין גישה למיקרופון",
  recUnsupported: "הדפדפן לא תומך בהקלטה",
  recHintIdle: "לחץ כדי להקליט הודעה מהטלפון ולשלוח לרמקול בבית.",
  recHintRecording: "מקליט… בחר שלח או שמור כשתסיים.",
  recSending: "שולח לרמקול…",
  recSaved: "ההקלטה נשמרה",
  recSent: "נשלח לרמקול",
  recFailed: "הקלטה נכשלה",
  recUploadPlay: "מעלה ומנגן…",
  kindUploads: "הועלה",
  kindRecordings: "הקלטה",
  kindSaved: "נשמר",
  kindExtra: "תיקייה",
  tracks: (n) => `${n} רצועות`,
  addCurrentUrl: "הוסף את הקישור הנוכחי",
};

const els = {
  hostLabel: $("#hostLabel"),
  btPower: $("#btPower"),
  btSubtitle: $("#btSubtitle"),
  btToggleRow: $("#btToggleRow"),
  btPanel: $("#btPanel"),
  btAccordion: $("#btAccordion"),
  connectedGroup: $("#connectedGroup"),
  devicesGroup: $("#devicesGroup"),
  scanBtn: $("#scanBtn"),
  ytUrl: $("#ytUrl"),
  playBtn: $("#playBtn"),
  playPauseBtn: $("#playPauseBtn"),
  prevBtn: $("#prevBtn"),
  nextBtn: $("#nextBtn"),
  stopBtn: $("#stopBtn"),
  nowTitle: $("#nowTitle"),
  nowSub: $("#nowSub"),
  playlistInfo: $("#playlistInfo"),
  queueToggle: $("#queueToggle"),
  queueList: $("#queueList"),
  seekBar: $("#seekBar"),
  timeCurrent: $("#timeCurrent"),
  timeDuration: $("#timeDuration"),
  volSlider: $("#volSlider"),
  volVal: $("#volVal"),
  noSpeakerMsg: $("#noSpeakerMsg"),
  ytSearch: $("#ytSearch"),
  searchBtn: $("#searchBtn"),
  searchResults: $("#searchResults"),
  statusLine: $("#statusLine"),
  toast: $("#toast"),
  busy: $("#busy"),
  busyText: $("#busyText"),
  adminSection: $("#adminSection"),
  inviteName: $("#inviteName"),
  createInviteBtn: $("#createInviteBtn"),
  refreshAccessBtn: $("#refreshAccessBtn"),
  lastInviteBox: $("#lastInviteBox"),
  lastInviteUrl: $("#lastInviteUrl"),
  copyInviteBtn: $("#copyInviteBtn"),
  adminInvitesGroup: $("#adminInvitesGroup"),
  adminDevicesGroup: $("#adminDevicesGroup"),
  authWhoami: $("#authWhoami"),
  saveUrlBtn: $("#saveUrlBtn"),
  queueUrlBtn: $("#queueUrlBtn"),
  sourceTabs: $("#sourceTabs"),
  uploadBtn: $("#uploadBtn"),
  uploadFile: $("#uploadFile"),
  libraryGroup: $("#libraryGroup"),
  playlistName: $("#playlistName"),
  createPlaylistBtn: $("#createPlaylistBtn"),
  playlistsGroup: $("#playlistsGroup"),
  recBtn: $("#recBtn"),
  recTimer: $("#recTimer"),
  recHint: $("#recHint"),
  recActions: $("#recActions"),
  recSendBtn: $("#recSendBtn"),
  recSaveBtn: $("#recSaveBtn"),
  recDiscardBtn: $("#recDiscardBtn"),
  recUploadBtn: $("#recUploadBtn"),
  recFile: $("#recFile"),
  recSecureNote: $("#recSecureNote"),
  historyGroup: $("#historyGroup"),
  plPicker: $("#plPicker"),
  plPickerList: $("#plPickerList"),
  plPickerCancel: $("#plPickerCancel"),
};

const LS_URL = "btSpeaker.lastUrl";
const LS_TOKEN = "btSpeaker.token";

let busyCount = 0;
let busySafetyTimer = null;
let statusTimer = null;
let volTimer = null;
let volDragging = false;
let authPrompted = false;
let isAdmin = false;
let myDeviceId = null;
let lastInviteUrl = "";
let hasSpeaker = false;
let playerPlaying = false;
let playerPaused = false;
let scrubbing = false;
let lastDuration = 0;
let pollMs = 4000;
let libraryCache = [];
let playlistsCache = [];
let savePollTimer = null;
let recRecorder = null;
let recChunks = [];
let recStream = null;
let recTimerId = null;
let recSeconds = 0;
let recPendingBlob = null;
let recPendingName = "recording.webm";
let plPickerCallback = null;
let statusReady = false;
let btPowerSyncing = false;
let skipDelta = 0;
let skipTimer = null;
let skipFlushing = false;
let queueOpen = false;

function getToken() {
  return localStorage.getItem(LS_TOKEN) || "";
}

function setToken(t) {
  if (t) localStorage.setItem(LS_TOKEN, t);
  else localStorage.removeItem(LS_TOKEN);
}

async function api(path, opts = {}) {
  const { timeoutMs = 25000, ...fetchOpts } = opts;
  const headers = { ...(fetchOpts.headers || {}) };
  const token = getToken();
  if (token) headers["X-Api-Token"] = token;
  const isForm = typeof FormData !== "undefined" && fetchOpts.body instanceof FormData;
  if (!isForm && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  let res;
  try {
    res = await fetch(path, {
      ...fetchOpts,
      headers,
      signal: ctrl.signal,
    });
  } catch (e) {
    clearTimeout(timer);
    if (e && e.name === "AbortError") {
      return { ok: false, error: STRINGS.requestTimeout, _timeout: true };
    }
    return { ok: false, error: String(e && e.message ? e.message : e) };
  }
  clearTimeout(timer);

  let data = null;
  try {
    data = await res.json();
  } catch {
    data = { ok: false, error: `HTTP ${res.status}` };
  }
  if (!res.ok && data && !data.error) data.error = `HTTP ${res.status}`;
  data._httpStatus = res.status;

  if (res.status === 401 && data?.auth_required && !authPrompted) {
    authPrompted = true;
    const entered = prompt(STRINGS.authPrompt);
    if (entered) {
      const raw = entered.trim();
      let tok = raw;
      try {
        if (raw.includes("token=")) {
          tok = new URL(raw, location.origin).searchParams.get("token") || raw;
        }
      } catch {
        /* bare token */
      }
      const redeemed = await redeemToken(tok);
      authPrompted = false;
      if (redeemed) return api(path, opts);
    } else {
      authPrompted = false;
      data._authCancelled = true;
    }
  }
  return data;
}

async function redeemToken(token) {
  if (!token) return false;
  try {
    const res = await fetch("/api/auth/redeem", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    const data = await res.json();
    if (data.ok && data.device_token) {
      setToken(data.device_token);
      toast(
        data.kind === "invite"
          ? STRINGS.deviceRegistered(data.device_name)
          : STRINGS.signedIn(data.device_name),
      );
      return true;
    }
    toast(data.error || STRINGS.inviteInvalid);
    return false;
  } catch {
    toast(STRINGS.authFailed);
    return false;
  }
}

function clearBusy() {
  busyCount = 0;
  clearTimeout(busySafetyTimer);
  busySafetyTimer = null;
  els.busy.hidden = true;
  els.busy.classList.remove("is-visible");
}

function setBusy(on, text) {
  busyCount += on ? 1 : -1;
  if (busyCount < 0) busyCount = 0;
  if (busyCount > 0) {
    els.busy.hidden = false;
    els.busy.classList.add("is-visible");
    if (text) els.busyText.textContent = text;
    clearTimeout(busySafetyTimer);
    // Never leave the overlay stuck if a BT call hangs
    busySafetyTimer = setTimeout(() => {
      clearBusy();
      toast(STRINGS.busyTimeout);
    }, 28000);
  } else {
    clearTimeout(busySafetyTimer);
    busySafetyTimer = null;
    els.busy.hidden = true;
    els.busy.classList.remove("is-visible");
  }
}

let toastTimer;
function toast(msg) {
  els.toast.hidden = false;
  els.toast.textContent = msg;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    els.toast.hidden = true;
  }, 2800);
}

function setStatus(msg) {
  els.statusLine.textContent = msg;
}

function iconFor(device) {
  if (device.is_audio || (device.icon || "").includes("audio")) return "🔊";
  if ((device.icon || "").includes("phone")) return "📱";
  return "📡";
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtTime(sec) {
  if (sec == null || !Number.isFinite(sec) || sec < 0) return "0:00";
  const s = Math.floor(sec);
  const m = Math.floor(s / 60);
  const r = s % 60;
  const h = Math.floor(m / 60);
  if (h > 0) {
    return `${h}:${String(m % 60).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
  }
  return `${m}:${String(r).padStart(2, "0")}`;
}

function setPlayPauseIcon(playing) {
  // "playing" → show pause; paused/stopped → show play
  els.playPauseBtn.classList.toggle("is-playing", !!playing);
  const playIcon = els.playPauseBtn.querySelector(".icon-play");
  const pauseIcon = els.playPauseBtn.querySelector(".icon-pause");
  if (playIcon) playIcon.hidden = !!playing;
  if (pauseIcon) pauseIcon.hidden = !playing;
  els.playPauseBtn.setAttribute("aria-label", playing ? "השהה" : "נגן");
  els.playPauseBtn.title = playing ? "השהה" : "נגן";
}

function updatePlaybackEnabled() {
  const canPlay = hasSpeaker;
  els.playBtn.disabled = !canPlay;
  els.searchBtn.disabled = false; // browsing/search OK; play gated in playUrl
  els.noSpeakerMsg.hidden = canPlay;
  els.playPauseBtn.disabled = !canPlay && !playerPlaying && !playerPaused;
}

function updateSeekUI(timePos, duration, percent) {
  if (scrubbing) return;
  const dur = Number(duration) || 0;
  lastDuration = dur;
  let pos = Number(timePos);
  if (!Number.isFinite(pos) && Number.isFinite(percent) && dur > 0) {
    pos = (percent / 100) * dur;
  }
  if (!Number.isFinite(pos)) pos = 0;

  els.timeCurrent.textContent = fmtTime(pos);
  els.timeDuration.textContent = dur > 0 ? fmtTime(dur) : (playerPlaying ? STRINGS.loadingTrack : "0:00");

  const max = 1000;
  els.seekBar.max = String(max);
  if (dur > 0) {
    els.seekBar.disabled = false;
    els.seekBar.value = String(Math.round((pos / dur) * max));
  } else if (Number.isFinite(percent)) {
    els.seekBar.disabled = false;
    els.seekBar.value = String(Math.round((percent / 100) * max));
  } else {
    els.seekBar.disabled = true;
    els.seekBar.value = "0";
  }
}

function renderQueue(p) {
  const items = p.queue || [];
  const count = p.playlist_count;
  const pos = p.playlist_pos;
  if (!items.length && (count == null || Number(count) < 2)) {
    els.queueToggle.hidden = true;
    els.queueList.hidden = true;
    return;
  }
  const cur = (pos != null ? Number(pos) : 0) + 1;
  const total = count || items.length;
  els.playlistInfo.textContent = STRINGS.playlistPos(cur, total);
  els.queueToggle.hidden = false;
  els.queueToggle.classList.toggle("is-open", queueOpen);
  els.queueToggle.title = STRINGS.queueHint;
  els.queueList.hidden = !queueOpen;
  if (!queueOpen) return;
  els.queueList.innerHTML = "";
  for (const it of items) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "queue-item" + (it.current ? " is-current" : "");
    btn.innerHTML = `
      <span class="queue-num">${Number(it.index) + 1}</span>
      <span class="cell-title" style="flex:1">${escapeHtml(it.title || "")}</span>
      <span class="queue-dot ${it.ready ? "" : "is-off"}" title="${it.ready ? "מוכן" : ""}"></span>`;
    btn.addEventListener("click", () => skipToIndex(it.index));
    els.queueList.appendChild(btn);
  }
}

function toggleQueue() {
  queueOpen = !queueOpen;
  els.queueToggle.classList.toggle("is-open", queueOpen);
  refreshStatus();
}

async function skipToIndex(index) {
  setBusy(true, STRINGS.loadingTrack);
  try {
    const data = await api("/api/skip", {
      method: "POST",
      body: JSON.stringify({ index }),
      timeoutMs: 130000,
    });
    if (!data.ok && !data.superseded) toast(data.error || STRINGS.nextFailed);
    await refreshStatus();
  } catch {
    toast(STRINGS.nextFailed);
  } finally {
    setBusy(false);
  }
}

function schedulePoll() {
  clearInterval(statusTimer);
  pollMs = playerPlaying ? 1500 : 4000;
  statusTimer = setInterval(refreshStatus, pollMs);
}

function renderConnected(devices) {
  const connected = (devices || []).filter((d) => d.connected);
  const group = els.connectedGroup;
  group.innerHTML = "";
  if (!connected.length) {
    group.innerHTML = `
      <div class="cell empty">
        <div class="cell-body">
          <div class="cell-title muted">${STRINGS.noSpeaker}</div>
        </div>
      </div>`;
    return;
  }
  for (const d of connected) {
    const cell = document.createElement("div");
    cell.className = "cell";
    cell.innerHTML = `
      <div class="cell-icon green"><span style="font-size:16px">${iconFor(d)}</span></div>
      <div class="cell-body">
        <div class="cell-title">${escapeHtml(d.name)}</div>
        <div class="cell-sub">${escapeHtml(d.address)}</div>
      </div>
      <div class="cell-actions-inline"></div>`;
    const actions = cell.querySelector(".cell-actions-inline");
    const disc = document.createElement("button");
    disc.type = "button";
    disc.className = "text-btn";
    disc.textContent = STRINGS.disconnect;
    disc.addEventListener("click", () => disconnectDevice(d.address));
    const forget = document.createElement("button");
    forget.type = "button";
    forget.className = "text-btn danger-text";
    forget.textContent = STRINGS.forget;
    forget.addEventListener("click", () => removeDevice(d.address, d.name));
    actions.appendChild(disc);
    actions.appendChild(forget);
    group.appendChild(cell);
  }
}

function renderDevices(devices) {
  const list = (devices || []).filter((d) => !d.connected);
  const audio = list.filter((d) => d.is_audio);
  const other = list.filter((d) => !d.is_audio);
  const ordered = [...audio, ...other];
  const group = els.devicesGroup;
  group.innerHTML = "";
  if (!ordered.length) {
    group.innerHTML = `
      <div class="cell empty">
        <div class="cell-body">
          <div class="cell-title muted">${STRINGS.noDevices}</div>
          <div class="cell-sub">${STRINGS.scanAgain}</div>
        </div>
      </div>`;
    return;
  }
  for (const d of ordered) {
    const cell = document.createElement("div");
    cell.className = "cell";
    const sub = [
      d.is_audio ? STRINGS.audio : d.icon || STRINGS.device,
      d.paired ? STRINGS.paired : null,
    ]
      .filter(Boolean)
      .join(" · ");
    cell.innerHTML = `
      <button type="button" class="device-btn">
        <div class="cell-icon ${d.is_audio ? "blue" : "orange"}"><span style="font-size:16px">${iconFor(d)}</span></div>
        <div class="cell-body">
          <div class="cell-title">${escapeHtml(d.name)}</div>
          <div class="cell-sub">${escapeHtml(sub)}</div>
        </div>
        <div class="cell-trailing">
          <span class="badge">${d.paired ? STRINGS.connect : STRINGS.pair}</span>
          <span class="chevron"></span>
        </div>
      </button>`;
    cell.querySelector("button").addEventListener("click", () => connectDevice(d.address, d.name));
    if (d.paired) {
      const forget = document.createElement("button");
      forget.type = "button";
      forget.className = "text-btn danger-text cell-forget";
      forget.textContent = STRINGS.forget;
      forget.addEventListener("click", (e) => {
        e.stopPropagation();
        removeDevice(d.address, d.name);
      });
      cell.appendChild(forget);
    }
    group.appendChild(cell);
  }
}

function applyStatus(data) {
  if (!data) return;
  if (data.host) els.hostLabel.textContent = data.host;
  statusReady = true;

  const b = data.bluetooth || {};
  if (!data.light) {
    const powered = !!b.powered;
    btPowerSyncing = true;
    els.btPower.checked = powered;
    btPowerSyncing = false;
    const connected = b.connected || [];
    hasSpeaker = Array.isArray(connected) && connected.length > 0;
    if (!hasSpeaker && Array.isArray(b.devices)) {
      hasSpeaker = b.devices.some((d) => d.connected);
    }
    if (!powered) {
      els.btSubtitle.textContent = STRINGS.btOff;
    } else if (connected.length) {
      els.btSubtitle.textContent = STRINGS.btConnectedTo(
        connected.map((c) => c.name).join(", "),
      );
    } else {
      els.btSubtitle.textContent = STRINGS.btOn;
    }

    if (Array.isArray(b.devices) && b.devices.length) {
      renderConnected(b.devices);
      renderDevices(b.devices);
    } else if (Array.isArray(b.connected)) {
      renderConnected(b.connected);
    }
  }

  const p = data.player || {};
  playerPlaying = !!p.playing;
  playerPaused = !!p.paused;
  setPlayPauseIcon(playerPlaying && !p.loading);

  if (p.loading) {
    els.nowTitle.textContent = p.title
      ? `${STRINGS.loadingTrack} ${p.title}`
      : STRINGS.loadingTrack;
    els.nowSub.hidden = true;
  } else if (p.playing) {
    els.nowTitle.textContent = p.title || STRINGS.playing;
    if (p.url) {
      els.nowSub.textContent = p.url;
      els.nowSub.hidden = true; // URL secondary — keep in DOM but hidden
    } else {
      els.nowSub.hidden = true;
    }
  } else if (p.paused) {
    els.nowTitle.textContent = `${p.title || STRINGS.paused} (${STRINGS.paused})`;
    els.nowSub.hidden = true;
  } else {
    els.nowTitle.textContent = STRINGS.nothingPlaying;
    els.nowSub.hidden = true;
  }

  renderQueue(p);

  updateSeekUI(p.time_pos, p.duration, p.percent);

  if (typeof data.volume === "number" && !volDragging) {
    els.volSlider.value = String(data.volume);
    els.volVal.textContent = `${data.volume}%`;
  }

  updatePlaybackEnabled();
  schedulePoll();

  const auth = data.auth || null;
  const wasAdmin = isAdmin;
  isAdmin = !!(auth && auth.admin);
  myDeviceId = auth?.device_id || null;
  if (auth) {
    els.authWhoami.textContent = auth.admin
      ? STRINGS.signedInAsAdmin(auth.device_name || "admin")
      : STRINGS.signedInAs(auth.device_name || "device");
  }
  els.adminSection.hidden = !isAdmin;
  if (isAdmin && !wasAdmin) {
    refreshAccessAdmin();
  }
}

function fmtWhen(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString("he-IL");
  } catch {
    return iso;
  }
}

function renderAdminInvites(invites) {
  const group = els.adminInvitesGroup;
  group.innerHTML = "";
  const open = (invites || []).filter((i) => i.open);
  if (!open.length) {
    group.innerHTML = `
      <div class="cell empty">
        <div class="cell-body">
          <div class="cell-title muted">${STRINGS.noOpenInvites}</div>
        </div>
      </div>`;
    return;
  }
  for (const inv of open) {
    const url = inv.invite_url || "";
    const cell = document.createElement("div");
    cell.className = "cell column";
    cell.innerHTML = `
      <div class="cell-title">${escapeHtml(inv.name)}</div>
      <div class="admin-meta">${escapeHtml(STRINGS.expires(fmtWhen(inv.expires_at)))}</div>
      <div class="invite-url">${escapeHtml(url)}</div>
      <div class="cell actions" style="padding-inline:0;padding-bottom:0"></div>`;
    const actions = cell.querySelector(".actions");
    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "pill";
    copyBtn.textContent = STRINGS.copy;
    copyBtn.addEventListener("click", () => copyText(url || inv.invite_url));
    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "pill danger";
    delBtn.textContent = STRINGS.cancel;
    delBtn.addEventListener("click", () => deleteInvite(inv.id));
    actions.appendChild(copyBtn);
    actions.appendChild(delBtn);
    group.appendChild(cell);
  }
}

function renderAdminDevices(devices) {
  const group = els.adminDevicesGroup;
  group.innerHTML = "";
  const list = devices || [];
  if (!list.length) {
    group.innerHTML = `
      <div class="cell empty">
        <div class="cell-body">
          <div class="cell-title muted">${STRINGS.none}</div>
        </div>
      </div>`;
    return;
  }
  for (const d of list) {
    const cell = document.createElement("div");
    cell.className = "cell";
    const you = d.id === myDeviceId ? STRINGS.you : "";
    const admin = d.admin ? STRINGS.admin : "";
    const revoked = d.revoked ? STRINGS.revokedTag : "";
    cell.innerHTML = `
      <div class="cell-body">
        <div class="cell-title">${escapeHtml(d.name)}${escapeHtml(admin)}${escapeHtml(you)}${escapeHtml(revoked)}</div>
        <div class="cell-sub">${escapeHtml(STRINGS.lastSeen(fmtWhen(d.last_seen)))}</div>
      </div>
      <div class="cell-actions-inline"></div>`;
    const actions = cell.querySelector(".cell-actions-inline");
    if (!d.revoked) {
      const rev = document.createElement("button");
      rev.type = "button";
      rev.className = "text-btn danger-text";
      rev.textContent = STRINGS.revoke;
      rev.disabled = d.admin && d.id === myDeviceId;
      rev.addEventListener("click", () => revokeAccessDevice(d.id, d.name));
      actions.appendChild(rev);
    }
    const del = document.createElement("button");
    del.type = "button";
    del.className = "text-btn danger-text";
    del.textContent = STRINGS.delete;
    del.addEventListener("click", () => deleteAccessDevice(d.id, d.name));
    actions.appendChild(del);
    group.appendChild(cell);
  }
}

async function copyText(text) {
  const value = (text || "").trim();
  if (!value) {
    toast(STRINGS.noLink);
    return false;
  }

  // Prefer Clipboard API when available (often fails on plain HTTP / Tailscale)
  try {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      await navigator.clipboard.writeText(value);
      toast(STRINGS.linkCopied);
      return true;
    }
  } catch {
    /* fall through */
  }

  // Fallback: textarea + execCommand('copy') — works on many HTTP contexts
  const ta = document.createElement("textarea");
  ta.value = value;
  ta.setAttribute("readonly", "");
  ta.style.cssText = "position:fixed;top:0;left:0;width:1px;height:1px;padding:0;border:0;opacity:0;";
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  ta.setSelectionRange(0, value.length);
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  document.body.removeChild(ta);

  if (ok) {
    toast(STRINGS.linkCopied);
    return true;
  }

  // Last resort: prompt so user can copy manually
  prompt(STRINGS.copyFailed, value);
  return false;
}

async function refreshAccessAdmin() {
  if (!isAdmin) return;
  const data = await api("/api/auth/admin/registry");
  if (!data.ok) {
    if (data.error) toast(data.error);
    return;
  }
  renderAdminInvites(data.invites);
  renderAdminDevices(data.devices);
}

async function createInvite() {
  const name = els.inviteName.value.trim();
  if (!name) {
    toast(STRINGS.enterDeviceName);
    return;
  }
  setBusy(true, STRINGS.creatingInvite);
  try {
    const data = await api("/api/auth/admin/invite", {
      method: "POST",
      body: JSON.stringify({ name, hours: 24 }),
    });
    if (!data.ok) {
      toast(data.error || STRINGS.failed);
      return;
    }
    lastInviteUrl = data.invite.invite_url || "";
    els.lastInviteUrl.textContent = lastInviteUrl;
    els.lastInviteBox.hidden = false;
    els.inviteName.value = "";
    toast(STRINGS.inviteReady(data.invite.name));
    setStatus(STRINGS.inviteCreated(data.invite.name));
    await refreshAccessAdmin();
  } finally {
    setBusy(false);
  }
}

async function revokeAccessDevice(id, name) {
  if (!confirm(STRINGS.revokeConfirm(name))) return;
  const data = await api("/api/auth/admin/revoke", {
    method: "POST",
    body: JSON.stringify({ device_id: id }),
  });
  if (!data.ok) toast(data.error || STRINGS.revokeFailed);
  else toast(STRINGS.revoked);
  await refreshAccessAdmin();
}

async function deleteAccessDevice(id, name) {
  if (!confirm(STRINGS.deleteConfirm(name))) return;
  const data = await api("/api/auth/admin/delete", {
    method: "POST",
    body: JSON.stringify({ device_id: id }),
  });
  if (!data.ok) toast(data.error || STRINGS.deleteFailed);
  else toast(STRINGS.deleted);
  await refreshAccessAdmin();
}

async function deleteInvite(id) {
  const data = await api("/api/auth/admin/delete-invite", {
    method: "POST",
    body: JSON.stringify({ invite_id: id }),
  });
  if (!data.ok) toast(data.error || STRINGS.cancelFailed);
  else toast(STRINGS.inviteCancelled);
  await refreshAccessAdmin();
}

async function refreshStatus(full = false) {
  try {
    const data = await api(full ? "/api/status" : "/api/status?light=1");
    if (data?.auth_required && !data.ok) {
      setStatus(STRINGS.authRequired);
      return null;
    }
    applyStatus(data);
    return data;
  } catch (e) {
    setStatus(STRINGS.cannotReach);
    return null;
  }
}

async function refreshDevices() {
  try {
    const data = await api("/api/bluetooth/devices");
    if (data.ok) {
      renderConnected(data.devices);
      renderDevices(data.devices);
      hasSpeaker = (data.devices || []).some((d) => d.connected);
      updatePlaybackEnabled();
    }
  } catch {
    /* ignore */
  }
}

async function togglePower() {
  if (btPowerSyncing) return;
  const on = els.btPower.checked;
  const prev = !on;
  setBusy(true, on ? STRINGS.turningBtOn : STRINGS.turningBtOff);
  try {
    const data = await api("/api/bluetooth/power", {
      method: "POST",
      body: JSON.stringify({ on }),
    });
    if (!data.ok || data._authCancelled || data._httpStatus === 401) {
      els.btPower.checked = prev;
      if (data.error && !data._authCancelled) toast(data.error);
      else if (data._authCancelled) toast(STRINGS.authRequired);
      else toast(STRINGS.powerFailed);
      return;
    }
    setStatus(on ? STRINGS.btOnStatus : STRINGS.btOffStatus);
    await refreshStatus(true);
    if (on) await refreshDevices();
  } catch (e) {
    toast(STRINGS.powerFailed);
    els.btPower.checked = prev;
  } finally {
    setBusy(false);
  }
}

async function scan() {
  els.scanBtn.disabled = true;
  setBusy(true, STRINGS.scanning);
  setStatus(STRINGS.scanningStatus);
  try {
    btPowerSyncing = true;
    els.btPower.checked = true;
    btPowerSyncing = false;
    const data = await api("/api/bluetooth/scan", {
      method: "POST",
      body: JSON.stringify({ seconds: 18, wait: true }),
    });
    if (data.devices) {
      renderConnected(data.devices);
      renderDevices(data.devices);
      hasSpeaker = (data.devices || []).some((d) => d.connected);
      updatePlaybackEnabled();
      const n = data.count || data.devices.length;
      setStatus(STRINGS.foundDevices(n));
      toast(STRINGS.foundDevices(n));
    } else if (data.error) {
      toast(data.error);
      setStatus(data.error);
    }
    await refreshStatus(true);
  } catch (e) {
    toast(STRINGS.scanFailed);
    setStatus(STRINGS.scanFailed);
  } finally {
    setBusy(false);
    els.scanBtn.disabled = false;
  }
}

async function connectDevice(address, name) {
  setBusy(true, STRINGS.connecting(name || address));
  setStatus(STRINGS.connecting(name || address));
  try {
    const data = await api("/api/bluetooth/connect", {
      method: "POST",
      body: JSON.stringify({ address }),
      timeoutMs: 60000,
    });
    if (data.ok) {
      toast(STRINGS.connectedTo(data.name || name));
      setStatus(STRINGS.connectedTo(data.name || name));
    } else {
      toast(data.error || STRINGS.connectFailed);
      setStatus(data.error || STRINGS.connectFailed);
    }
  } catch {
    toast(STRINGS.connectFailed);
  } finally {
    setBusy(false);
  }
  refreshDevices();
  refreshStatus();
}

async function disconnectDevice(address) {
  setBusy(true, STRINGS.disconnecting);
  try {
    const data = await api("/api/bluetooth/disconnect", {
      method: "POST",
      body: JSON.stringify({ address }),
      timeoutMs: 20000,
    });
    if (data._timeout || (data.error && !data.ok && data._httpStatus >= 500)) {
      toast(data.error || STRINGS.disconnectFailed);
    } else {
      toast(STRINGS.disconnected);
      setStatus(STRINGS.disconnected);
    }
  } catch {
    toast(STRINGS.disconnectFailed);
  } finally {
    // Hide overlay BEFORE slow device refresh (list_devices can take a long time)
    setBusy(false);
  }
  refreshDevices();
  refreshStatus();
}

async function removeDevice(address, name) {
  if (!confirm(STRINGS.forgetConfirm(name || address))) return;
  setBusy(true, STRINGS.forgetting);
  try {
    const data = await api("/api/bluetooth/remove", {
      method: "POST",
      body: JSON.stringify({ address }),
      timeoutMs: 20000,
    });
    if (data.ok) {
      toast(STRINGS.deviceForgotten);
      setStatus(`${STRINGS.deviceForgotten}: ${name || address}`);
    } else {
      toast(data.error || STRINGS.forgetFailed);
    }
  } catch {
    toast(STRINGS.forgetFailed);
  } finally {
    setBusy(false);
  }
  refreshDevices();
  refreshStatus();
}

function looksLikeNoSpeakerError(err) {
  if (!err) return false;
  const s = String(err).toLowerCase();
  return (
    /no\s*(bt|bluetooth)?\s*speaker/.test(s) ||
    /speaker\s*(not\s*)?(connected|available|required)/.test(s) ||
    /bluetooth\s*speaker\s*(required|needed|missing)/.test(s) ||
    /not\s*connected.*speaker/.test(s) ||
    s.includes("אין רמקול") ||
    s.includes("רמקול לא מחובר") ||
    s.includes("no_bt_speaker") ||
    s.includes("no-bt-speaker")
  );
}

async function playUrl(url, title) {
  if (!url) {
    toast(STRINGS.pasteUrlFirst);
    return;
  }
  if (!hasSpeaker) {
    toast(STRINGS.noBtSpeaker);
    return;
  }
  localStorage.setItem(LS_URL, url);
  setBusy(true, STRINGS.startingStream);
  setStatus(STRINGS.startingPlayback);
  try {
    const body = { url };
    if (title) body.title = title;
    const data = await api("/api/play", {
      method: "POST",
      body: JSON.stringify(body),
      timeoutMs: 130000,
    });
    if (data.ok) {
      toast(data.title ? STRINGS.playingTitle(data.title) : STRINGS.playingStatus);
      setStatus(data.title ? STRINGS.playingTitle(data.title) : STRINGS.playingStatus);
      els.nowTitle.textContent = data.title || STRINGS.playing;
      els.nowSub.textContent = url;
      els.nowSub.hidden = true;
      if (!data.sink) {
        toast(STRINGS.noBtSpeaker);
      }
    } else {
      const err = data.error || STRINGS.playFailed;
      if (looksLikeNoSpeakerError(err)) {
        toast(STRINGS.noBtSpeaker);
      } else {
        toast(err);
      }
      setStatus(err);
      // Don't pretend playing
      playerPlaying = false;
      setPlayPauseIcon(false);
    }
    await refreshStatus();
  } catch {
    toast(STRINGS.playFailed);
  } finally {
    setBusy(false);
  }
}

async function play() {
  await playUrl(els.ytUrl.value.trim());
}

async function stop() {
  try {
    await api("/api/stop", { method: "POST", body: "{}" });
    setStatus(STRINGS.stopped);
    await refreshStatus();
  } catch {
    toast(STRINGS.stopFailed);
  }
}

async function pause() {
  const data = await api("/api/pause", { method: "POST", body: "{}" });
  if (!data.ok) toast(data.error || STRINGS.pauseFailed);
  await refreshStatus();
}

async function resume() {
  const data = await api("/api/resume", { method: "POST", body: "{}" });
  if (!data.ok) toast(data.error || STRINGS.resumeFailed);
  await refreshStatus();
}

async function togglePlayPause() {
  if (!statusReady) {
    await refreshStatus();
  }
  if (playerPlaying) {
    await pause();
  } else if (playerPaused) {
    await resume();
  } else {
    // Don't fire /api/play (which stop()s the current track) just because
    // the UI hasn't synced yet after a refresh.
    const data = await refreshStatus();
    const p = data && data.player;
    if (p && (p.playing || p.loading)) return;
    if (p && p.paused) {
      await resume();
      return;
    }
    await play();
  }
}

function transportClick(fn) {
  return () => {
    if (Date.now() < transportArmedAt) return;
    fn();
  };
}

function queueSkip(delta) {
  skipDelta += delta;
  clearTimeout(skipTimer);
  skipTimer = setTimeout(flushSkip, 180);
}

async function flushSkip() {
  if (skipFlushing) return;
  const n = skipDelta;
  skipDelta = 0;
  if (!n) return;
  skipFlushing = true;
  setBusy(true, STRINGS.loadingTrack);
  try {
    const data = await api("/api/skip", {
      method: "POST",
      body: JSON.stringify({ delta: n }),
      timeoutMs: 130000,
    });
    if (data.superseded) {
      /* a newer skip won — ignore */
    } else if (!data.ok) {
      toast(data.error || (n > 0 ? STRINGS.nextFailed : STRINGS.prevFailed));
    }
    await refreshStatus();
  } catch {
    toast(n > 0 ? STRINGS.nextFailed : STRINGS.prevFailed);
  } finally {
    skipFlushing = false;
    setBusy(false);
    if (skipDelta) flushSkip();
  }
}

function nextTrack() {
  queueSkip(1);
}

function prevTrack() {
  queueSkip(-1);
}

async function seekTo(seconds, percent) {
  const body = {};
  if (seconds != null && Number.isFinite(seconds)) body.seconds = seconds;
  if (percent != null && Number.isFinite(percent)) body.percent = percent;
  const data = await api("/api/seek", {
    method: "POST",
    body: JSON.stringify(body),
  });
  if (!data.ok) toast(data.error || STRINGS.seekFailed);
  await refreshStatus();
}

function onSeekInput() {
  scrubbing = true;
  const max = Number(els.seekBar.max) || 1000;
  const ratio = Number(els.seekBar.value) / max;
  if (lastDuration > 0) {
    els.timeCurrent.textContent = fmtTime(ratio * lastDuration);
  } else {
    els.timeCurrent.textContent = fmtTime(0);
  }
}

async function onSeekCommit() {
  scrubbing = true;
  const max = Number(els.seekBar.max) || 1000;
  const ratio = Number(els.seekBar.value) / max;
  const percent = ratio * 100;
  const seconds = lastDuration > 0 ? ratio * lastDuration : null;
  try {
    await seekTo(seconds, percent);
  } finally {
    scrubbing = false;
  }
}

function onVolumeInput() {
  const v = els.volSlider.value;
  els.volVal.textContent = `${v}%`;
  volDragging = true;
  clearTimeout(volTimer);
  volTimer = setTimeout(async () => {
    try {
      const data = await api("/api/volume", {
        method: "POST",
        body: JSON.stringify({ percent: Number(v) }),
      });
      if (data && typeof data.volume === "number") {
        els.volSlider.value = String(data.volume);
        els.volVal.textContent = `${data.volume}%`;
      } else if (data && data.ok === false) {
        toast(data.error || "ווליום נכשל");
      }
    } catch {
      toast("ווליום נכשל");
    } finally {
      volDragging = false;
    }
  }, 150);
}

function renderSearchResults(results) {
  const box = els.searchResults;
  box.innerHTML = "";
  if (!results || !results.length) {
    box.hidden = false;
    box.innerHTML = `<div class="cell empty"><div class="cell-body"><div class="cell-title muted">${STRINGS.noResults}</div></div></div>`;
    return;
  }
  box.hidden = false;
  for (const r of results) {
    const title = r.title || r.name || r.url || "—";
    const url = r.url || r.link || "";
    const row = document.createElement("div");
    row.className = "search-result";
    const play = document.createElement("button");
    play.type = "button";
    play.className = "search-play";
    play.innerHTML = `
      <div class="cell-title">${escapeHtml(title)}</div>
      ${r.channel || r.uploader ? `<div class="cell-sub">${escapeHtml(r.channel || r.uploader)}</div>` : ""}
    `;
    play.addEventListener("click", () => {
      if (!url) return;
      els.ytUrl.value = url;
      localStorage.setItem(LS_URL, url);
      playUrl(url, title);
    });
    const actions = document.createElement("div");
    actions.className = "search-actions";
    const qBtn = miniIconBtn("queue", STRINGS.addToQueue, () => enqueueUrl(url, title, false));
    const sBtn = miniIconBtn("save", STRINGS.saveToLibrary, () => saveUrl(url));
    actions.appendChild(qBtn);
    actions.appendChild(sBtn);
    row.appendChild(play);
    row.appendChild(actions);
    box.appendChild(row);
  }
}

function miniIconBtn(kind, label, onClick) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "icon-mini";
  btn.title = label;
  btn.setAttribute("aria-label", label);
  btn.innerHTML = kind === "save" ? ICON_SAVE : ICON_QUEUE;
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    onClick();
  });
  return btn;
}

const ICON_QUEUE = `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M3 6h18v2H3V6zm0 5h12v2H3v-2zm0 5h12v2H3v-2zm14-1.5v3h3v2h-3v3h-2v-3h-3v-2h3v-3h2z"/></svg>`;
const ICON_SAVE = `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M17 3H5a2 2 0 0 0-2 2v16l7-3 7 3V5a2 2 0 0 0-2-2zm0 15.76-5-2.15-5 2.15V5h10v13.76z"/></svg>`;

async function enqueueUrl(url, title, expand) {
  if (!url) {
    toast(STRINGS.pasteUrlFirst);
    return;
  }
  if (!hasSpeaker) {
    toast(STRINGS.noBtSpeaker);
    return;
  }
  const data = await api("/api/queue", {
    method: "POST",
    body: JSON.stringify({ url, title, expand: expand !== false }),
    timeoutMs: expand === false ? 20000 : 90000,
  });
  if (!data.ok) {
    if (looksLikeNoSpeakerError(data.error)) toast(STRINGS.noBtSpeaker);
    else toast(data.error || STRINGS.queueFailed);
    return;
  }
  toast(STRINGS.queued(title || data.title));
  queueOpen = true;
  await refreshStatus();
}

async function enqueueFile(fileId, title) {
  if (!hasSpeaker) {
    toast(STRINGS.noBtSpeaker);
    return;
  }
  const data = await api("/api/queue", {
    method: "POST",
    body: JSON.stringify({ file_id: fileId, title }),
  });
  if (!data.ok) {
    toast(data.error || STRINGS.queueFailed);
    return;
  }
  toast(STRINGS.queued(title));
  queueOpen = true;
  await refreshStatus();
}

async function queueCurrentUrl() {
  await enqueueUrl(els.ytUrl.value.trim(), null, true);
}

async function searchYoutube() {
  const q = els.ytSearch.value.trim();
  if (!q) {
    toast(STRINGS.enterSearch);
    return;
  }
  setBusy(true, STRINGS.searching);
  try {
    const data = await api("/api/search", {
      method: "POST",
      body: JSON.stringify({ q, query: q, limit: 8 }),
    });
    if (!data.ok) {
      toast(data.error || STRINGS.searchFailed);
      return;
    }
    const results = data.results || data.items || data.videos || [];
    renderSearchResults(results);
  } catch {
    toast(STRINGS.searchFailed);
  } finally {
    setBusy(false);
  }
}

function kindLabel(kind) {
  if (kind === "recordings") return STRINGS.kindRecordings;
  if (kind === "saved") return STRINGS.kindSaved;
  if (kind === "extra") return STRINGS.kindExtra;
  return STRINGS.kindUploads;
}

function fmtSize(n) {
  const x = Number(n) || 0;
  if (x < 1024) return `${x} B`;
  if (x < 1024 * 1024) return `${(x / 1024).toFixed(1)} KB`;
  return `${(x / (1024 * 1024)).toFixed(1)} MB`;
}

function switchTab(name) {
  document.querySelectorAll(".seg-btn").forEach((btn) => {
    const on = btn.dataset.tab === name;
    btn.classList.toggle("is-active", on);
    btn.setAttribute("aria-selected", on ? "true" : "false");
  });
  document.querySelectorAll(".tab-pane").forEach((pane) => {
    pane.hidden = pane.dataset.tab !== name;
  });
  if (name === "library") {
    refreshLibrary();
    refreshPlaylists();
  } else if (name === "history") {
    refreshHistory();
  } else if (name === "record") {
    updateRecSecureNote();
  }
}

function emptyCell(title, sub) {
  return `
    <div class="cell empty">
      <div class="cell-body">
        <div class="cell-title muted">${escapeHtml(title)}</div>
        ${sub ? `<div class="cell-sub">${escapeHtml(sub)}</div>` : ""}
      </div>
    </div>`;
}

async function refreshLibrary() {
  const data = await api("/api/library");
  if (!data.ok) return;
  libraryCache = data.files || [];
  renderLibrary(libraryCache);
  const job = data.save_job || {};
  if (job.status === "running") {
    scheduleSavePoll();
  } else if (job.status === "ok") {
    clearTimeout(savePollTimer);
    if (job.title) toast(STRINGS.saveDone(job.title));
  } else if (job.status === "error" && job.error) {
    clearTimeout(savePollTimer);
    toast(job.error);
  }
}

function renderLibrary(files) {
  const group = els.libraryGroup;
  group.innerHTML = "";
  if (!files.length) {
    group.innerHTML = emptyCell(STRINGS.noFiles, STRINGS.dropHint);
    return;
  }
  for (const f of files) {
    const cell = document.createElement("div");
    cell.className = "cell";
    const sub = [kindLabel(f.kind), fmtSize(f.size)].filter(Boolean).join(" · ");
    cell.innerHTML = `
      <button type="button" class="file-row">
        <div class="cell-body">
          <div class="cell-title">${escapeHtml(f.title || f.name)}</div>
          <div class="cell-sub">${escapeHtml(sub)}</div>
        </div>
      </button>
      <div class="cell-actions-inline"></div>`;
    cell.querySelector(".file-row").addEventListener("click", () => playFile(f.id, f.title || f.name));
    const actions = cell.querySelector(".cell-actions-inline");
    const queue = document.createElement("button");
    queue.type = "button";
    queue.className = "text-btn";
    queue.textContent = "תור";
    queue.title = STRINGS.addToQueue;
    queue.addEventListener("click", (e) => {
      e.stopPropagation();
      enqueueFile(f.id, f.title || f.name);
    });
    const add = document.createElement("button");
    add.type = "button";
    add.className = "text-btn";
    add.textContent = "+";
    add.title = STRINGS.addToPlaylist;
    add.addEventListener("click", (e) => {
      e.stopPropagation();
      pickPlaylist((pl) => addToPlaylist(pl.id, { kind: "file", file_id: f.id, title: f.title || f.name }));
    });
    const del = document.createElement("button");
    del.type = "button";
    del.className = "text-btn danger-text";
    del.textContent = STRINGS.delete;
    del.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteLibraryFile(f.id, f.title || f.name);
    });
    actions.appendChild(queue);
    actions.appendChild(add);
    actions.appendChild(del);
    group.appendChild(cell);
  }
}

async function playFile(fileId, title) {
  if (!hasSpeaker) {
    toast(STRINGS.noBtSpeaker);
    return;
  }
  setBusy(true, STRINGS.startingPlayback);
  try {
    const data = await api("/api/play", {
      method: "POST",
      body: JSON.stringify({ file_id: fileId }),
    });
    if (data.ok) {
      toast(STRINGS.playingTitle(data.title || title || STRINGS.playingStatus));
      setStatus(STRINGS.playingTitle(data.title || title || ""));
    } else if (looksLikeNoSpeakerError(data.error)) {
      toast(STRINGS.noBtSpeaker);
    } else {
      toast(data.error || STRINGS.playFailed);
    }
    await refreshStatus();
  } catch {
    toast(STRINGS.playFailed);
  } finally {
    setBusy(false);
  }
}

async function deleteLibraryFile(fileId, name) {
  if (!confirm(STRINGS.deleteFileConfirm(name || fileId))) return;
  const data = await api("/api/library/delete", {
    method: "POST",
    body: JSON.stringify({ file_id: fileId }),
  });
  if (!data.ok) {
    toast(data.error || STRINGS.deleteFailed);
    return;
  }
  toast(STRINGS.deleted);
  await refreshLibrary();
}

async function uploadFiles(fileList, { play = false, kind = "uploads" } = {}) {
  const files = [...(fileList || [])];
  if (!files.length) return;
  setBusy(true, play ? STRINGS.recUploadPlay : STRINGS.uploading);
  try {
    for (const file of files) {
      const fd = new FormData();
      fd.append("file", file, file.name);
      fd.append("kind", kind);
      if (play) fd.append("play", "true");
      const path = play ? "/api/record" : "/api/library";
      const data = await api(path, { method: "POST", body: fd, timeoutMs: 90000 });
      if (!data.ok) {
        toast(data.error || STRINGS.uploadFailed);
        continue;
      }
      if (play) {
        if (data.played) toast(STRINGS.recSent);
        else if (data.play_error) toast(data.play_error);
        else toast(STRINGS.recSaved);
      } else {
        toast(STRINGS.uploaded);
      }
    }
    await refreshLibrary();
    await refreshStatus();
  } finally {
    setBusy(false);
  }
}

function scheduleSavePoll() {
  clearTimeout(savePollTimer);
  savePollTimer = setTimeout(async () => {
    const data = await api("/api/library");
    if (!data.ok) return;
    libraryCache = data.files || [];
    if (!document.getElementById("tab-library").hidden) renderLibrary(libraryCache);
    const job = data.save_job || {};
    if (job.status === "running") {
      scheduleSavePoll();
    } else if (job.status === "ok") {
      toast(STRINGS.saveDone(job.title));
      if (!document.getElementById("tab-library").hidden) renderLibrary(libraryCache);
    } else if (job.status === "error") {
      toast(job.error || STRINGS.saveFailed);
    }
  }, 2500);
}

async function saveUrl(url) {
  const href = (url || "").trim();
  if (!href) {
    toast(STRINGS.pasteUrlToSave);
    return;
  }
  const data = await api("/api/library/save-url", {
    method: "POST",
    body: JSON.stringify({ url: href }),
  });
  if (!data.ok) {
    toast(data.error || STRINGS.saveFailed);
    return;
  }
  toast(STRINGS.saveStarted);
  scheduleSavePoll();
}

async function saveCurrentUrl() {
  await saveUrl(els.ytUrl.value || "");
}

async function refreshPlaylists() {
  const data = await api("/api/playlists");
  if (!data.ok) return;
  playlistsCache = data.playlists || [];
  renderPlaylists(playlistsCache);
}

function renderPlaylists(list) {
  const group = els.playlistsGroup;
  group.innerHTML = "";
  if (!list.length) {
    group.innerHTML = emptyCell(STRINGS.noPlaylists);
    return;
  }
  for (const pl of list) {
    const items = pl.items || [];
    const wrap = document.createElement("div");
    wrap.className = "cell column";
    wrap.innerHTML = `
      <div class="pl-item-row">
        <div class="cell-body">
          <div class="cell-title">${escapeHtml(pl.name)}</div>
          <div class="cell-sub">${escapeHtml(STRINGS.tracks(items.length))}</div>
        </div>
        <div class="cell-actions-inline"></div>
      </div>
      <div class="pl-tracks"></div>`;
    const actions = wrap.querySelector(".cell-actions-inline");
    const playBtn = document.createElement("button");
    playBtn.type = "button";
    playBtn.className = "text-btn";
    playBtn.textContent = "נגן";
    playBtn.addEventListener("click", () => playPlaylist(pl.id, pl.name));
    const addUrl = document.createElement("button");
    addUrl.type = "button";
    addUrl.className = "text-btn";
    addUrl.textContent = "+ קישור";
    addUrl.title = STRINGS.addCurrentUrl;
    addUrl.addEventListener("click", () => {
      const url = (els.ytUrl.value || "").trim();
      if (!url) {
        toast(STRINGS.pasteUrlFirst);
        return;
      }
      addToPlaylist(pl.id, { kind: "url", url, title: url });
    });
    const del = document.createElement("button");
    del.type = "button";
    del.className = "text-btn danger-text";
    del.textContent = STRINGS.delete;
    del.addEventListener("click", () => deletePlaylist(pl.id, pl.name));
    actions.appendChild(playBtn);
    actions.appendChild(addUrl);
    actions.appendChild(del);
    const tracks = wrap.querySelector(".pl-tracks");
    items.forEach((it, idx) => {
      const row = document.createElement("div");
      row.className = "pl-item-row";
      row.style.paddingTop = "8px";
      const title = it.title || it.url || it.file_id || "—";
      const playFrom = document.createElement("button");
      playFrom.type = "button";
      playFrom.className = "pl-track-btn";
      playFrom.innerHTML = `<div class="cell-sub">${escapeHtml(title)}</div>`;
      playFrom.title = STRINGS.playFromHere;
      playFrom.addEventListener("click", () => playPlaylist(pl.id, pl.name, idx));
      const rm = document.createElement("button");
      rm.type = "button";
      rm.className = "text-btn danger-text";
      rm.textContent = "×";
      rm.addEventListener("click", () => removePlaylistItem(pl.id, it.id));
      row.appendChild(playFrom);
      row.appendChild(rm);
      tracks.appendChild(row);
    });
    group.appendChild(wrap);
  }
}

async function createPlaylist() {
  const name = (els.playlistName.value || "").trim();
  if (!name) {
    toast(STRINGS.enterPlaylistName);
    return;
  }
  const data = await api("/api/playlists", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  if (!data.ok) {
    toast(data.error || STRINGS.failed);
    return;
  }
  els.playlistName.value = "";
  toast(STRINGS.playlistCreated(name));
  await refreshPlaylists();
}

async function deletePlaylist(id, name) {
  if (!confirm(STRINGS.deleteConfirm(name || id))) return;
  const data = await api(`/api/playlists/${encodeURIComponent(id)}`, { method: "DELETE", body: "{}" });
  if (!data.ok) {
    toast(data.error || STRINGS.deleteFailed);
    return;
  }
  toast(STRINGS.deleted);
  await refreshPlaylists();
}

async function addToPlaylist(playlistId, item) {
  const data = await api(`/api/playlists/${encodeURIComponent(playlistId)}/items`, {
    method: "POST",
    body: JSON.stringify(item),
  });
  if (!data.ok) {
    toast(data.error || STRINGS.failed);
    return;
  }
  toast(STRINGS.addedToPlaylist);
  await refreshPlaylists();
}

async function removePlaylistItem(playlistId, itemId) {
  const data = await api(
    `/api/playlists/${encodeURIComponent(playlistId)}/items/${encodeURIComponent(itemId)}`,
    { method: "DELETE", body: "{}" },
  );
  if (!data.ok) {
    toast(data.error || STRINGS.deleteFailed);
    return;
  }
  await refreshPlaylists();
}

async function playPlaylist(id, name, startIndex) {
  if (!hasSpeaker) {
    toast(STRINGS.noBtSpeaker);
    return;
  }
  setBusy(true, STRINGS.startingPlayback);
  try {
    const body = { playlist_id: id };
    if (startIndex != null) body.start_index = startIndex;
    const data = await api("/api/play/playlist", {
      method: "POST",
      body: JSON.stringify(body),
    });
    if (data.ok) {
      toast(STRINGS.playingPlaylist(data.title || name));
      setStatus(STRINGS.playingPlaylist(data.title || name));
    } else if (looksLikeNoSpeakerError(data.error)) {
      toast(STRINGS.noBtSpeaker);
    } else {
      toast(data.error || STRINGS.playFailed);
    }
    await refreshStatus();
  } catch {
    toast(STRINGS.playFailed);
  } finally {
    setBusy(false);
  }
}

function pickPlaylist(cb) {
  if (!playlistsCache.length) {
    toast(STRINGS.createPlaylistFirst);
    switchTab("library");
    return;
  }
  if (playlistsCache.length === 1) {
    cb(playlistsCache[0]);
    return;
  }
  plPickerCallback = cb;
  els.plPickerList.innerHTML = "";
  for (const pl of playlistsCache) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "pl-pick-btn";
    btn.textContent = pl.name;
    btn.addEventListener("click", () => {
      const fn = plPickerCallback;
      closePlaylistPicker();
      if (fn) fn(pl);
    });
    els.plPickerList.appendChild(btn);
  }
  els.plPicker.hidden = false;
}

function closePlaylistPicker() {
  els.plPicker.hidden = true;
  plPickerCallback = null;
}

async function refreshHistory() {
  const data = await api("/api/history");
  if (!data.ok) return;
  renderHistory(data.items || []);
}

function renderHistory(items) {
  const group = els.historyGroup;
  group.innerHTML = "";
  if (!items.length) {
    group.innerHTML = emptyCell(STRINGS.noHistory);
    return;
  }
  for (const h of items) {
    const cell = document.createElement("div");
    cell.className = "cell";
    const when = fmtWhen(h.played_at);
    cell.innerHTML = `
      <button type="button" class="file-row">
        <div class="cell-body">
          <div class="cell-title">${escapeHtml(h.title || "—")}</div>
          <div class="cell-sub">${escapeHtml(when)}</div>
        </div>
      </button>`;
    cell.querySelector(".file-row").addEventListener("click", () => replayHistory(h));
    group.appendChild(cell);
  }
}

async function replayHistory(h) {
  if (h.source === "playlist" && h.playlist_id) {
    await playPlaylist(h.playlist_id, h.title);
    return;
  }
  if (h.file_id) {
    await playFile(h.file_id, h.title);
    return;
  }
  if (h.url) {
    els.ytUrl.value = h.url;
    await playUrl(h.url, h.title);
  }
}

function updateRecSecureNote() {
  const ok = window.isSecureContext && !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
  els.recSecureNote.hidden = ok;
}

function recMime() {
  const types = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];
  if (!window.MediaRecorder || !MediaRecorder.isTypeSupported) return "";
  return types.find((t) => MediaRecorder.isTypeSupported(t)) || "";
}

function recExt(mime) {
  if ((mime || "").includes("mp4")) return "m4a";
  if ((mime || "").includes("ogg")) return "ogg";
  return "webm";
}

function setRecTimer(sec) {
  recSeconds = sec;
  els.recTimer.textContent = fmtTime(sec);
}

function stopRecTracks() {
  if (recStream) {
    recStream.getTracks().forEach((t) => t.stop());
    recStream = null;
  }
  if (recTimerId) {
    clearInterval(recTimerId);
    recTimerId = null;
  }
}

async function startRecording() {
  updateRecSecureNote();
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    toast(STRINGS.recNeedHttps);
    return;
  }
  if (!window.MediaRecorder) {
    toast(STRINGS.recUnsupported);
    return;
  }
  try {
    recStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    toast(STRINGS.recDenied);
    return;
  }
  recChunks = [];
  recPendingBlob = null;
  const mime = recMime();
  try {
    recRecorder = mime ? new MediaRecorder(recStream, { mimeType: mime }) : new MediaRecorder(recStream);
  } catch {
    toast(STRINGS.recUnsupported);
    stopRecTracks();
    return;
  }
  recRecorder.ondataavailable = (e) => {
    if (e.data && e.data.size) recChunks.push(e.data);
  };
  recRecorder.onstop = () => {
    const type = recRecorder?.mimeType || mime || "audio/webm";
    recPendingBlob = new Blob(recChunks, { type });
    recPendingName = `recording_${Date.now()}.${recExt(type)}`;
    stopRecTracks();
    els.recBtn.classList.remove("is-recording");
    els.recActions.hidden = false;
    els.recHint.textContent = STRINGS.recHintRecording;
  };
  recRecorder.start(250);
  els.recBtn.classList.add("is-recording");
  els.recActions.hidden = true;
  els.recHint.textContent = STRINGS.recHintRecording;
  setRecTimer(0);
  recTimerId = setInterval(() => setRecTimer(recSeconds + 1), 1000);
}

function stopRecording() {
  if (recRecorder && recRecorder.state === "recording") {
    recRecorder.stop();
  }
}

function discardRecording() {
  recPendingBlob = null;
  recChunks = [];
  if (recRecorder && recRecorder.state === "recording") recRecorder.stop();
  stopRecTracks();
  els.recBtn.classList.remove("is-recording");
  els.recActions.hidden = true;
  els.recHint.textContent = STRINGS.recHintIdle;
  setRecTimer(0);
}

async function finishRecording(play) {
  if (recRecorder && recRecorder.state === "recording") {
    await new Promise((resolve) => {
      recRecorder.addEventListener("stop", resolve, { once: true });
      recRecorder.stop();
    });
  }
  if (!recPendingBlob || !recPendingBlob.size) {
    toast(STRINGS.recFailed);
    discardRecording();
    return;
  }
  setBusy(true, play ? STRINGS.recSending : STRINGS.uploading);
  try {
    const fd = new FormData();
    fd.append("file", recPendingBlob, recPendingName);
    fd.append("play", play ? "true" : "false");
    const data = await api("/api/record", { method: "POST", body: fd, timeoutMs: 90000 });
    if (!data.ok) {
      toast(data.error || STRINGS.recFailed);
      return;
    }
    if (play) {
      if (data.played) toast(STRINGS.recSent);
      else toast(data.play_error || STRINGS.recSaved);
    } else {
      toast(STRINGS.recSaved);
    }
    discardRecording();
    await refreshStatus();
  } catch {
    toast(STRINGS.recFailed);
  } finally {
    setBusy(false);
  }
}

function onRecBtn() {
  if (recRecorder && recRecorder.state === "recording") {
    stopRecording();
    return;
  }
  startRecording();
}

function toggleBtPanel() {
  const open = els.btPanel.hidden;
  els.btPanel.hidden = !open;
  els.btToggleRow.setAttribute("aria-expanded", open ? "true" : "false");
  els.btAccordion.classList.toggle("open", open);
  if (open) refreshDevices();
}

function bind() {
  els.btPower.addEventListener("change", togglePower);
  els.btToggleRow.addEventListener("click", (e) => {
    // Don't toggle panel when interacting with the switch
    if (e.target.closest(".ios-switch")) return;
    toggleBtPanel();
  });
  els.scanBtn.addEventListener("click", scan);
  els.playBtn.addEventListener("click", play);
  els.queueUrlBtn.addEventListener("click", queueCurrentUrl);
  els.playPauseBtn.addEventListener("click", transportClick(togglePlayPause));
  els.stopBtn.addEventListener("click", transportClick(stop));
  els.prevBtn.addEventListener("click", transportClick(prevTrack));
  els.nextBtn.addEventListener("click", transportClick(nextTrack));
  els.queueToggle.addEventListener("click", toggleQueue);
  els.volSlider.addEventListener("input", onVolumeInput);
  els.volSlider.addEventListener("pointerdown", () => {
    volDragging = true;
  });
  els.volSlider.addEventListener("pointerup", () => {
    // keep true until the debounce request finishes
  });

  els.seekBar.addEventListener("pointerdown", () => {
    scrubbing = true;
  });
  els.seekBar.addEventListener("touchstart", () => {
    scrubbing = true;
  }, { passive: true });
  els.seekBar.addEventListener("input", onSeekInput);
  els.seekBar.addEventListener("change", onSeekCommit);

  els.ytUrl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") play();
  });
  els.ytUrl.addEventListener("change", () => {
    const v = els.ytUrl.value.trim();
    if (v) localStorage.setItem(LS_URL, v);
  });
  els.searchBtn.addEventListener("click", searchYoutube);
  els.ytSearch.addEventListener("keydown", (e) => {
    if (e.key === "Enter") searchYoutube();
  });
  els.saveUrlBtn.addEventListener("click", saveCurrentUrl);
  els.sourceTabs.addEventListener("click", (e) => {
    const btn = e.target.closest(".seg-btn");
    if (!btn) return;
    switchTab(btn.dataset.tab);
  });
  els.uploadBtn.addEventListener("click", () => els.uploadFile.click());
  els.uploadFile.addEventListener("change", () => {
    uploadFiles(els.uploadFile.files);
    els.uploadFile.value = "";
  });
  els.createPlaylistBtn.addEventListener("click", createPlaylist);
  els.playlistName.addEventListener("keydown", (e) => {
    if (e.key === "Enter") createPlaylist();
  });
  els.recBtn.addEventListener("click", onRecBtn);
  els.recSendBtn.addEventListener("click", () => finishRecording(true));
  els.recSaveBtn.addEventListener("click", () => finishRecording(false));
  els.recDiscardBtn.addEventListener("click", discardRecording);
  els.recUploadBtn.addEventListener("click", () => els.recFile.click());
  els.recFile.addEventListener("change", () => {
    uploadFiles(els.recFile.files, { play: true, kind: "recordings" });
    els.recFile.value = "";
  });
  els.plPickerCancel.addEventListener("click", closePlaylistPicker);
  els.plPicker.addEventListener("click", (e) => {
    if (e.target === els.plPicker) closePlaylistPicker();
  });
  els.createInviteBtn.addEventListener("click", createInvite);
  els.refreshAccessBtn.addEventListener("click", refreshAccessAdmin);
  els.copyInviteBtn.addEventListener("click", () =>
    copyText(lastInviteUrl || els.lastInviteUrl.textContent),
  );
  els.inviteName.addEventListener("keydown", (e) => {
    if (e.key === "Enter") createInvite();
  });
}

function registerPwa() {
  if (!("serviceWorker" in navigator)) return;
  // SW needs a secure context (HTTPS / localhost). On plain HTTP (LAN/Tailscale)
  // registration usually fails — iOS "Add to Home Screen" still works via meta tags.
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
      /* ignore — expected on http:// */
    });
  });
}

async function init() {
  clearBusy();
  registerPwa();

  const saved = localStorage.getItem(LS_URL);
  if (saved) els.ytUrl.value = saved;

  const params = new URLSearchParams(location.search);
  const qToken = params.get("token");
  if (qToken) {
    params.delete("token");
    const clean = location.pathname + (params.toString() ? `?${params}` : "") + location.hash;
    history.replaceState(null, "", clean);
    await redeemToken(qToken);
  }

  bind();
  transportArmedAt = Date.now() + 700;
  els.nowTitle.textContent = STRINGS.loadingTrack;
  setPlayPauseIcon(false);
  updatePlaybackEnabled();
  updateRecSecureNote();
  await refreshStatus();
  schedulePoll();
}

init();
