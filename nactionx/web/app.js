'use strict';
/* NactionX Downloader: interfaz */

/* ================= constantes y utilidades ================= */
const svg = (inner, extra = '') => `<svg class="i" viewBox="0 0 24 24" aria-hidden="true"${extra}>${inner}</svg>`;
const I = {
  play: svg('<polygon points="7 4 20 12 7 20 7 4"/>'),
  pause: svg('<rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/>'),
  x: svg('<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>'),
  retry: svg('<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>'),
  trash: svg('<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>'),
  folder: svg('<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>'),
  top: svg('<line x1="12" y1="21" x2="12" y2="9"/><polyline points="6 15 12 9 18 15"/><line x1="5" y1="4" x2="19" y2="4"/>'),
  copy: svg('<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>'),
  check: svg('<polyline points="20 6 9 17 4 12"/>'),
  alert: svg('<circle cx="12" cy="12" r="9"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>'),
  info: svg('<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>'),
  video: svg('<rect x="2" y="5" width="15" height="14" rx="2"/><path d="m17 10 5-3v10l-5-3"/>'),
  audio: svg('<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>'),
  plus: svg('<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>'),
  cut: svg('<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/>'),
  list: svg('<line x1="9" y1="6" x2="21" y2="6"/><line x1="9" y1="12" x2="21" y2="12"/><line x1="9" y1="18" x2="21" y2="18"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>'),
  grip: svg('<circle cx="9" cy="6" r="1.6"/><circle cx="15" cy="6" r="1.6"/><circle cx="9" cy="12" r="1.6"/><circle cx="15" cy="12" r="1.6"/><circle cx="9" cy="18" r="1.6"/><circle cx="15" cy="18" r="1.6"/>'),
  pen: svg('<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>'),
  undo: svg('<path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-15-6.7L3 13"/>'),
  back: svg('<line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>'),
  log: svg('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>'),
  warn: svg('<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>'),
};
const ACTIVE = ['starting', 'downloading', 'processing'];
const STATUS = {queued: 'En cola', starting: 'Iniciando', downloading: 'Descargando', processing: 'Procesando', done: 'Completado', error: 'Error', paused: 'Pausado', canceled: 'Cancelado'};
const QUALITIES = [['best', 'Máxima'], ['4320', '4320p (8K)'], ['2160', '2160p (4K)'], ['1440', '1440p (2K)'], ['1080', '1080p'], ['720', '720p'], ['480', '480p'], ['360', '360p'], ['240', '240p'], ['144', '144p']];
const SITE_RE = /(youtube\.com|youtu\.be|vimeo\.com|tiktok\.com|instagram\.com|instagr\.am|ig\.me|twitter\.com|x\.com|twitch\.tv|soundcloud\.com|facebook\.com|fb\.watch|dailymotion\.com|reddit\.com|bilibili\.com|kick\.com|bandcamp\.com|threads\.net|vk\.com)/i;
const URL_RE = /https?:\/\/[^\s<>"']+/g;
const BAD_CHARS = /[<>:"/\\|?*\x00-\x1f]/g;
const BAD_TEST = /[<>:"/\\|?*\x00-\x1f]/;
const IS_MAC = /Mac|iPhone|iPad/i.test(navigator.platform || navigator.userAgent);
const MOD = IS_MAC ? '⌘' : 'Ctrl';

const S = {
  app: {}, settings: {}, components: {}, folder: {}, jobs: [], byId: new Map(), paused: false, srev: null, prev: null,
  filter: 'all', view: 'downloads', prevStatus: {}, dragging: null, preview: null, lastSearch: null, sel: new Set(),
  fails: 0, history: [], token: 0, pending: {}, clip: '', appUpdate: {},
};
const nodes = new Map();
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const ls = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
};
const sleep = ms => new Promise(r => setTimeout(r, ms));

const TOKEN = (() => {
  const match = location.hash.match(/t=([\w-]+)/);
  if (match) {
    try { sessionStorage.setItem('nx-token', match[1]); } catch {}
    history.replaceState(null, '', location.pathname);
    return match[1];
  }
  try { return sessionStorage.getItem('nx-token') || ''; } catch { return ''; }
})();

async function api(path, body) {
  const init = {headers: {'X-NactionX-Token': TOKEN}};
  if (body !== undefined) {
    init.method = 'POST';
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  const response = await fetch(path, init);
  let data = {};
  try { data = await response.json(); } catch {}
  if (!response.ok) {
    const error = new Error(data.error || `Error ${response.status}`);
    Object.assign(error, {kind: data.kind, detail: data.detail, status: response.status});
    throw error;
  }
  return data;
}

function bytes(n) { n = +n || 0; if (n <= 0) return '—'; const u = ['B', 'KB', 'MB', 'GB', 'TB']; let i = 0; while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; } return (n >= 100 || i === 0 ? n.toFixed(0) : n.toFixed(1)) + ' ' + u[i]; }
function dur(s) { s = Math.round(+s || 0); if (!s) return ''; const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(x).padStart(2, '0'); }
function longDur(s) { s = Math.round(+s || 0); const h = Math.floor(s / 3600), m = Math.round(s % 3600 / 60); return h ? `${h} h ${m} min` : `${m} min`; }
function views(n) { if (!n) return ''; if (n >= 1e9) return (n / 1e9).toFixed(1).replace('.0', '') + ' mil M visualizaciones'; if (n >= 1e6) return (n / 1e6).toFixed(1).replace('.0', '') + ' M visualizaciones'; if (n >= 1e3) return Math.round(n / 1e3) + ' mil visualizaciones'; return n + ' visualizaciones'; }
function ymd(d) { if (!d || d.length !== 8) return ''; return new Date(+d.slice(0, 4), +d.slice(4, 6) - 1, +d.slice(6, 8)).toLocaleDateString('es-ES', {day: 'numeric', month: 'short', year: 'numeric'}); }
function ago(t) { if (!t) return ''; const s = Date.now() / 1000 - t; if (s < 60) return 'hace un momento'; if (s < 3600) return `hace ${Math.floor(s / 60)} min`; if (s < 86400) return `hace ${Math.floor(s / 3600)} h`; return new Date(t * 1000).toLocaleDateString('es-ES', {day: 'numeric', month: 'short', year: 'numeric'}); }
function short(p) { return String(p || '').replace(/^[A-Z]:\\Users\\[^\\]+/i, '~').replace(/^\/Users\/[^/]+/, '~'); }
function fileBase(p) { return String(p || '').split(/[\\/]/).pop().replace(/\.[^.]+$/, ''); }
function fileExt(p) { const m = String(p || '').match(/(\.[^.\\/]+)$/); return m ? m[1] : ''; }
function extFor(o) { o = o || S.settings; return o.mode === 'audio' ? (o.audio_format === 'original' ? '' : '.' + o.audio_format) : '.' + (o.container || 'mp4'); }
const isUrl = t => /^https?:\/\/\S+$/i.test(String(t).trim());
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch {}
  const area = document.createElement('textarea');
  area.value = text; area.style.position = 'fixed'; area.style.opacity = '0';
  document.body.appendChild(area); area.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch {}
  area.remove();
  return ok;
}

/* ================= avisos y diálogos ================= */
function toast(msg, type = 'info', sub = '') {
  const el = document.createElement('div');
  el.className = 'toast ' + type;
  el.setAttribute('role', type === 'err' ? 'alert' : 'status');
  el.innerHTML = (type === 'ok' ? I.check : type === 'err' ? I.alert : I.info) + `<div>${esc(msg)}${sub ? `<small>${esc(sub)}</small>` : ''}</div>`;
  $('#toasts').appendChild(el);
  setTimeout(() => { el.style.transition = 'opacity .3s'; el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, type === 'err' ? 7000 : 3800);
}
const toastBuffer = {done: [], error: []};
let toastTimer;
function bufferToast(kind, text) { toastBuffer[kind].push(text); clearTimeout(toastTimer); toastTimer = setTimeout(flushToasts, 1200); }
function flushToasts() {
  const {done, error} = toastBuffer;
  if (done.length === 1) toast('Descarga completada', 'ok', done[0]);
  else if (done.length > 1) toast(`${done.length} descargas completadas`, 'ok');
  if (error.length === 1) toast('Error en la descarga', 'err', error[0]);
  else if (error.length > 1) toast(`${error.length} descargas con error`, 'err', 'Revisa la pestaña Fallidas');
  toastBuffer.done = []; toastBuffer.error = [];
}

function openDialog({title, body = '', html = '', buttons = [], wide = false, onOpen}) {
  return new Promise(resolve => {
    const bg = $('#dialog'), box = $('#dialogBox');
    const previous = document.activeElement;
    box.className = 'card modal' + (wide ? ' wide' : '');
    box.setAttribute('aria-labelledby', 'dlgTitle');
    box.innerHTML = `<h3 id="dlgTitle">${esc(title)}</h3>${body ? `<p>${esc(body)}</p>` : ''}${html}<div class="modal-foot">${buttons.map((b, i) => `<button class="btn ${b.cls || ''}" data-i="${i}">${esc(b.label)}</button>`).join('')}</div>`;
    bg.hidden = false;
    const cancelValue = () => { const b = buttons.find(x => x.cancel); return b ? b.value : null; };
    const close = value => {
      bg.hidden = true; box.innerHTML = '';
      document.removeEventListener('keydown', onKey, true);
      bg.onmousedown = null;
      if (previous && previous.focus) previous.focus();
      resolve(value);
    };
    const onKey = e => {
      if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); close(cancelValue()); }
      else if (e.key === 'Enter' && !['TEXTAREA', 'BUTTON'].includes(e.target.tagName)) {
        const index = buttons.findIndex(b => b.default);
        if (index >= 0) { e.preventDefault(); e.stopPropagation(); box.querySelector(`[data-i="${index}"]`).click(); }
      }
    };
    document.addEventListener('keydown', onKey, true);
    bg.onmousedown = e => { if (e.target === bg) close(cancelValue()); };
    box.querySelectorAll('[data-i]').forEach(btn => btn.addEventListener('click', () => {
      const b = buttons[+btn.dataset.i];
      close(b.getValue ? b.getValue(box) : b.value);
    }));
    if (onOpen) onOpen(box, close);
    const focusable = box.querySelector('input,textarea') || box.querySelector(`[data-i="${Math.max(0, buttons.findIndex(b => b.default))}"]`);
    if (focusable) focusable.focus();
  });
}
const ask = (title, body, okLabel = 'Aceptar', danger = false) => openDialog({
  title, body,
  buttons: [{label: 'Cancelar', cls: 'ghost', value: false, cancel: true}, {label: okLabel, cls: danger ? 'danger-fill' : 'primary', value: true, default: true}],
});

/* ================= arranque y estado ================= */
function setConn(ok) {
  $('#conn').classList.toggle('off', !ok);
  $('#connText').textContent = ok ? 'Motor activo' : 'Sin conexión';
  if (ok) $('#offline').hidden = true;
}

async function bootstrap() {
  const b = await api('/api/bootstrap');
  S.app = b.app; S.settings = b.settings; S.components = b.components; S.folder = b.folder;
  S.appUpdate = b.app_update || {};
  buildControls(); renderFolder(); renderEngine(); renderIssues(); renderAbout(); renderAppUpdate();
  $('#verText').textContent = `v${b.app.version} · motor ${b.components.ytdlp}`;
  if (S.settings.check_updates) setTimeout(() => checkUpdates(true), 4000);
  // La comprobación del arranque la lanza el servidor: se recoge su resultado un poco después.
  if (S.settings.check_app_updates) setTimeout(pollAppUpdate, 6000);
}

async function poll() {
  let delay = 1500;
  try {
    const query = S.srev == null ? '' : `?srev=${S.srev}&prev=${S.prev}`;
    applyState(await api('/api/state' + query));
    S.fails = 0; setConn(true);
    delay = S.jobs.some(j => ACTIVE.includes(j.status)) ? 600 : 1500;
  } catch (e) {
    S.fails++; setConn(false);
    if (e.status === 401 || e.status === 403) { $('#offline').textContent = 'La sesión no es válida. Cierra la ventana y vuelve a abrir la app.'; $('#offline').hidden = false; delay = 5000; }
    else if (S.fails > 2) $('#offline').hidden = false;
  }
  setTimeout(poll, delay);
}

function applyState(st) {
  if (!st || typeof st.srev !== 'number') return;
  S.paused = !!st.paused;
  if (Array.isArray(st.jobs)) {
    S.jobs = st.jobs;
    S.byId = new Map(st.jobs.map(j => [j.id, j]));
    detectTransitions();
    renderQueue();
  } else if (st.progress) {
    for (const [id, fields] of Object.entries(st.progress)) {
      const job = S.byId.get(id);
      if (!job) continue;
      Object.assign(job, fields);
      const el = nodes.get(id);
      if (el) updateJob(el, job);
    }
  }
  S.srev = st.srev; S.prev = st.prev;
  renderStats();
}

function detectTransitions() {
  const seen = new Set();
  for (const j of S.jobs) {
    seen.add(j.id);
    const before = S.prevStatus[j.id];
    if (before && before !== j.status) {
      const name = j.custom_name || j.title;
      if (j.status === 'done') { bufferToast('done', name); if (S.view === 'history') loadHistory(); }
      else if (j.status === 'error') bufferToast('error', `${name}: ${j.error}`);
    }
    S.prevStatus[j.id] = j.status;
  }
  for (const id of Object.keys(S.prevStatus)) if (!seen.has(id)) delete S.prevStatus[id];
}

const isRetrying = j => j.status === 'queued' && j.retry_at && j.retry_at * 1000 > Date.now();

function renderStats() {
  const c = {active: 0, queued: 0, done: 0, error: 0, canceled: 0};
  let speed = 0, progress = 0;
  for (const j of S.jobs) {
    if (ACTIVE.includes(j.status)) { c.active++; speed += j.speed || 0; progress += j.progress || 0; }
    else if (j.status === 'queued' || j.status === 'paused') c.queued++;
    else if (j.status === 'done') c.done++;
    else if (j.status === 'error') c.error++;
    else c.canceled++;
  }
  $('#stSpeed').textContent = speed ? bytes(speed) + '/s' : '0 B/s';
  $('#stActive').textContent = c.active; $('#stQueued').textContent = c.queued; $('#stDone').textContent = c.done; $('#stErr').textContent = c.error;
  const navCount = $('#navCount'); navCount.hidden = !(c.active + c.queued); navCount.textContent = c.active + c.queued;
  document.title = c.active ? `(${Math.round(progress / c.active)}%) ${plural(c.active, 'descargando', 'descargando')} · NactionX Downloader` : (S.paused && c.queued ? 'En pausa · NactionX Downloader' : 'NactionX Downloader');
  const tabs = {all: S.jobs.length, active: c.active, queued: c.queued, done: c.done, error: c.error + c.canceled};
  $$('#qTabs button').forEach(b => b.querySelector('i').textContent = tabs[b.dataset.f]);
  const pauseAll = $('#btnPauseAll');
  const html = S.paused ? I.play + 'Reanudar todo' : I.pause + 'Pausar todo';
  if (pauseAll.dataset.h !== html) { pauseAll.innerHTML = html; pauseAll.dataset.h = html; }
  pauseAll.classList.toggle('primary', S.paused);
}

/* ================= cola ================= */
function matches(j, f) {
  if (f === 'all') return true;
  if (f === 'active') return ACTIVE.includes(j.status);
  if (f === 'queued') return j.status === 'queued' || j.status === 'paused';
  if (f === 'done') return j.status === 'done';
  return j.status === 'error' || j.status === 'canceled';
}

function renderQueue() {
  if (S.dragging) return;
  const list = $('#qList');
  const visible = S.jobs.filter(j => matches(j, S.filter));
  const ids = new Set(visible.map(j => j.id));
  for (const [id, el] of nodes) { if (!ids.has(id)) { el.remove(); nodes.delete(id); } }
  let position = 0; const positions = {};
  for (const j of S.jobs) if (j.status === 'queued') positions[j.id] = ++position;
  visible.forEach((j, i) => {
    let el = nodes.get(j.id);
    if (!el) { el = createJob(j); nodes.set(j.id, el); }
    el._pos = positions[j.id];
    updateJob(el, j);
    if (list.children[i] !== el) list.insertBefore(el, list.children[i] || null);
  });
  renderEmpty(visible.length);
}

function renderEmpty(count) {
  const empty = $('#qEmpty');
  empty.hidden = count > 0;
  if (count) return;
  const filtered = S.jobs.length > 0;
  $('#emptyTitle').textContent = filtered ? 'Nada en esta pestaña' : 'La cola está vacía';
  $('#emptyText').textContent = filtered ? 'Cambia de pestaña para ver el resto de descargas.'
    : 'Pega un enlace arriba, arrastra enlaces a la ventana o usa el modo Lote. La cola se guarda al cerrar y las descargas continúan donde se quedaron.';
  $('#emptyKeys').hidden = filtered;
  $('#emptyKeys').innerHTML = `<span><kbd>${MOD}</kbd> <kbd>V</kbd> pegar y analizar</span><span><kbd>${MOD}</kbd> <kbd>B</kbd> lote</span><span><kbd>Esc</kbd> cerrar vista previa</span>`;
}

function createJob(j) {
  const el = document.createElement('div');
  el.className = 'job'; el.dataset.id = j.id; el.draggable = true;
  el.innerHTML = `<div class="grip" title="Arrastra para reordenar" aria-hidden="true">${I.grip}</div>
    <div class="jthumb"><img alt="" loading="lazy" referrerpolicy="no-referrer"><span class="kind"></span><button class="ov" data-act="play" title="Reproducir" aria-label="Reproducir">${I.play}</button></div>
    <div class="jmain"><div class="jtop"><div class="jtitle"></div><span class="pill"></span></div>
    <div class="jmeta"></div><div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="100"><i></i></div><div class="jstats tnum"></div></div>
    <div class="jact"></div>`;
  return el;
}

function actionsFor(j) {
  const b = (act, icon, title, cls = '') => `<button class="ibtn ${cls}" data-act="${act}" title="${title}" aria-label="${title}">${icon}</button>`;
  const rename = b('rename', I.pen, j.status === 'done' ? 'Cambiar el nombre del archivo' : 'Elegir el nombre del archivo');
  switch (j.status) {
    case 'queued':
      return rename + b('top', I.top, 'Descargar a continuación') + b('pause', I.pause, 'Pausar') + b('copy', I.copy, 'Copiar enlace') + b('remove', I.x, 'Quitar de la cola', 'bad');
    case 'starting': case 'downloading': case 'processing':
      return rename + b('pause', I.pause, 'Pausar') + b('log', I.log, 'Ver registro') + b('folder', I.folder, 'Abrir carpeta de destino') + b('cancel', I.x, 'Cancelar y borrar lo descargado', 'bad');
    case 'paused':
      return rename + b('resume', I.play, 'Reanudar', 'ok') + b('top', I.top, 'Descargar a continuación') + b('copy', I.copy, 'Copiar enlace') + b('cancel', I.x, 'Cancelar', 'bad');
    case 'done':
      return rename + b('play', I.play, 'Reproducir', 'ok') + b('reveal', I.folder, 'Mostrar en la carpeta') + b('log', I.log, 'Ver registro') + b('remove', I.trash, 'Quitar de la lista');
    case 'error':
      return rename + b('retry', I.retry, 'Reintentar', 'ok') + b('log', I.log, 'Ver registro y detalles') + b('copy', I.copy, 'Copiar enlace') + b('remove', I.trash, 'Quitar de la lista', 'bad');
    default:
      return rename + b('retry', I.retry, 'Volver a descargar', 'ok') + b('copy', I.copy, 'Copiar enlace') + b('remove', I.trash, 'Quitar de la lista');
  }
}

function updateJob(el, j) {
  const status = j.status, o = j.options || {}, retrying = isRetrying(j);
  const key = status + (retrying ? ':r' : '');
  if (el.dataset.st !== key) {
    el.className = 'job st-' + status + (el.classList.contains('dragging') ? ' dragging' : '');
    el.dataset.st = key;
    const pill = el.querySelector('.pill');
    pill.className = 'pill ' + (retrying ? 'retry' : status);
    pill.innerHTML = (status === 'processing' || status === 'starting' ? '<span class="spin s"></span>' : '') + (retrying ? 'Reintentando' : STATUS[status]);
    el.querySelector('.jact').innerHTML = actionsFor(j);
  }
  const img = el.querySelector('img');
  if (j.thumbnail && img.getAttribute('src') !== j.thumbnail) img.src = j.thumbnail;
  const title = el.querySelector('.jtitle'), shown = j.custom_name || j.title;
  if (!el.dataset.editing && title.textContent !== shown) { title.textContent = shown; title.title = j.custom_name ? `${j.custom_name}\nOriginal: ${j.title}` : j.title; }
  const kind = o.mode === 'audio' ? I.audio : I.video;
  const kindEl = el.querySelector('.kind'); if (kindEl.dataset.m !== o.mode) { kindEl.innerHTML = kind; kindEl.dataset.m = o.mode; }

  const label = j.format_label || (o.mode === 'audio' ? (o.audio_format || '').toUpperCase() : `${(o.container || '').toUpperCase()} · ${o.quality === 'best' ? 'Máxima' : o.quality + 'p'}`);
  const extras = [o.start || o.end ? `✂ ${o.start || '0:00'}–${o.end || 'fin'}` : '', o.sponsorblock ? 'SponsorBlock' : '', o.mode !== 'audio' && o.subtitles ? 'Subtítulos' : ''].filter(Boolean);
  const metaHtml = `<span class="chip">${esc(label)}</span>${extras.map(x => `<span class="chip">${esc(x)}</span>`).join('')}${j.custom_name ? '<span class="chip accent">✎ Nombre propio</span>' : ''}${j.uploader ? `<span class="ell">${esc(j.uploader)}</span>` : ''}${j.duration ? `<span>${dur(j.duration)}</span>` : ''}`;
  const meta = el.querySelector('.jmeta'); if (meta.dataset.h !== metaHtml) { meta.innerHTML = metaHtml; meta.dataset.h = metaHtml; }

  const pct = status === 'done' ? 100 : status === 'queued' && !j.progress ? 0 : Math.max(j.progress || 0, status === 'starting' ? 2 : 0);
  el.querySelector('.bar i').style.width = pct + '%';
  el.querySelector('.bar').setAttribute('aria-valuenow', String(Math.round(pct)));

  let s;
  const pctText = `<b>${(j.progress || 0).toFixed(1)}%</b>`;
  if (status === 'downloading') s = `${pctText}<span>${bytes(j.downloaded)} / ${bytes(j.total)}</span><span>${j.speed ? bytes(j.speed) + '/s' : '—'}</span><span>${j.eta != null ? 'Quedan ' + dur(j.eta || 1) : ''}</span><span class="phase">${esc(j.phase)}</span>`;
  else if (status === 'processing' || status === 'starting') s = `<span class="phase"><span class="spin s"></span>${esc(j.phase || 'Preparando')}</span>${j.total ? `<span>${bytes(j.total)}</span>` : ''}`;
  else if (retrying) s = `<span class="warn">${esc(j.phase)} en ${Math.max(1, Math.ceil(j.retry_at - Date.now() / 1000))} s</span><span class="err">${esc(j.error)}</span>`;
  else if (status === 'queued') s = `<span>Posición ${el._pos || '—'} en la cola</span><span class="path">${esc(short(o.folder))}</span>`;
  else if (status === 'paused') s = `${j.progress ? pctText : ''}<span>${j.total ? bytes(j.downloaded) + ' / ' + bytes(j.total) : ''}</span><span>${j.paused_by === 'global' ? 'Pausado con «Pausar todo»' : 'Continuará desde donde se quedó'}</span>`;
  else if (status === 'done') s = `<b class="ok-t">${bytes(j.filesize)}</b><span>${ago(j.finished)}</span>${j.note && j.note !== 'Completado' ? `<span>${esc(j.note)}</span>` : ''}<span class="path" title="${esc(j.filepath)}">${esc(short(j.filepath))}</span>`;
  else if (status === 'error') s = `<span class="err">${esc(j.error)}</span><button class="linkbtn" data-act="log">Detalles</button>`;
  else s = '<span>Cancelado</span>';
  const stats = el.querySelector('.jstats'); if (stats.dataset.h !== s) { stats.innerHTML = s; stats.dataset.h = s; }
}

setInterval(() => {
  for (const j of S.jobs) if (j.status === 'queued' && j.retry_at) { const el = nodes.get(j.id); if (el) updateJob(el, j); }
}, 1000);

async function jobAct(id, act) {
  const j = S.byId.get(id); if (!j) return;
  if (act === 'rename') return startRename(j);
  if (act === 'log') return openLog(j);
  try {
    if (act === 'play') return await api('/api/open', {path: j.filepath, mode: 'file'});
    if (act === 'reveal') return await api('/api/open', {path: j.filepath, mode: 'reveal'});
    if (act === 'folder') return await api('/api/open', {path: (j.options || {}).folder, mode: 'folder'});
    if (act === 'copy') { await copyText(j.url); ls.set('lastClip', j.url); return toast('Enlace copiado'); }
    await api('/api/job', {id, action: act});
    if (act === 'remove') { const el = nodes.get(id); if (el) { el.remove(); nodes.delete(id); } }
    refreshSoon();
  } catch (e) { toast(e.message, 'err'); }
}
let refreshTimer;
function refreshSoon() { clearTimeout(refreshTimer); refreshTimer = setTimeout(async () => { try { applyState(await api(`/api/state?srev=-1`)); } catch {} }, 120); }

async function openLog(j) {
  let lines = [];
  try { lines = (await api('/api/job-log?id=' + encodeURIComponent(j.id))).log || []; } catch {}
  const time = t => new Date(t * 1000).toLocaleTimeString('es-ES');
  const text = lines.map(l => `[${time(l.t)}] ${l.level === 'info' ? '' : l.level.toUpperCase() + ': '}${l.msg}`).join('\n');
  const errorHtml = j.status === 'error' || j.error ? `<p>${esc(j.error)}</p>${j.error_detail && j.error_detail !== j.error ? `<div class="detail">${esc(j.error_detail)}</div>` : ''}` : '';
  const logHtml = lines.length ? lines.map(l => `<div class="${l.level}"><time>${time(l.t)}</time>${esc(l.msg)}</div>`).join('')
    : '<div>No hay registro para esta descarga en esta sesión.</div>';
  const choice = await openDialog({
    title: j.custom_name || j.title, wide: true,
    html: `${errorHtml}<div class="logview">${logHtml}</div>`,
    buttons: [{label: 'Copiar', cls: 'ghost', value: 'copy'}, {label: 'Cerrar', cls: 'primary', value: null, default: true, cancel: true}],
    onOpen: box => { const view = box.querySelector('.logview'); view.scrollTop = view.scrollHeight; },
  });
  if (choice === 'copy' && await copyText([j.error_detail, text].filter(Boolean).join('\n\n'))) toast('Registro copiado');
}

/* edición en línea de nombres */
function inlineEdit(target, current, ext, onSave, onEnd) {
  target.innerHTML = `<span class="rn"><input class="rename" spellcheck="false" autocomplete="off" aria-label="Nombre del archivo"><span class="ext">${esc(ext)}</span></span>`;
  const input = target.querySelector('input');
  input.value = current; input.focus(); input.select();
  let finished = false;
  const finish = async save => {
    if (finished) return; finished = true;
    const value = input.value.trim();
    if (save && value && value !== current) {
      try { await onSave(value); } catch (e) { toast('No se pudo cambiar el nombre', 'err', e.message); }
    }
    onEnd();
  };
  input.addEventListener('input', () => { if (BAD_TEST.test(input.value)) input.value = input.value.replace(BAD_CHARS, ''); });
  input.addEventListener('keydown', e => {
    e.stopPropagation();
    if (e.key === 'Enter') { e.preventDefault(); finish(true); }
    if (e.key === 'Escape') { e.preventDefault(); finish(false); }
  });
  input.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); });
  input.addEventListener('blur', () => finish(true));
}
async function renameApi(id, name) {
  const r = await api('/api/rename', {id, name});
  if (r.applied === 'now') toast('Archivo renombrado', 'ok', r.name + fileExt(r.path));
  else if (r.applied === 'later') toast('Nombre guardado', 'ok', 'Se aplicará en cuanto termine la descarga');
  else toast('Nombre guardado', 'ok', 'Se usará al descargar');
  return r;
}
function startRename(j) {
  const el = nodes.get(j.id); if (!el || el.dataset.editing) return;
  el.dataset.editing = '1'; el.draggable = false;
  const onDisk = j.status === 'done' && j.filepath;
  const current = j.custom_name || (onDisk ? fileBase(j.filepath) : j.title.replace(BAD_CHARS, ''));
  inlineEdit(el.querySelector('.jtitle'), current, onDisk ? fileExt(j.filepath) : extFor(j.options),
    async v => { await renameApi(j.id, v); },
    () => { delete el.dataset.editing; el.draggable = true; el.querySelector('.jtitle').textContent = ''; updateJob(el, S.byId.get(j.id) || j); refreshSoon(); if (S.view === 'history') loadHistory(); });
}

/* ================= opciones ================= */
function buildControls() {
  $('#oQuality').innerHTML = QUALITIES.map(([v, l]) => `<option value="${v}">${l}</option>`).join('');
  $$('[data-concurrency]').forEach(sel => sel.innerHTML = [1, 2, 3, 4, 5, 6, 8].map(n => `<option value="${n}">${n}</option>`).join(''));
  syncControls();
}

function syncControls() {
  const s = S.settings;
  $$('#modeSeg button').forEach(b => { b.classList.toggle('on', b.dataset.mode === s.mode); b.setAttribute('aria-pressed', String(b.dataset.mode === s.mode)); });
  $$('[data-for="video"]').forEach(e => e.hidden = s.mode !== 'video');
  $$('[data-for="audio"]').forEach(e => e.hidden = s.mode !== 'audio');
  if (s.mode === 'audio') $('#bitrateField').hidden = !['mp3', 'm4a', 'opus'].includes(s.audio_format);
  const webm = s.container === 'webm';
  const h264 = $('#oCodec option[value="h264"]');
  h264.disabled = webm;
  h264.textContent = webm ? 'H.264 (no compatible con WEBM)' : 'H.264 (máxima compatibilidad)';
  const quality = $('#oQuality');
  if (s.quality && ![...quality.options].some(o => o.value === String(s.quality))) quality.insertAdjacentHTML('beforeend', `<option value="${esc(s.quality)}">${esc(s.quality)}p</option>`);
  $$('[data-key]').forEach(el => {
    const value = s[el.dataset.key];
    if (el.type === 'checkbox') el.checked = !!value;
    else if (document.activeElement !== el) el.value = value ?? '';
  });
  const preset = $('#tplPreset');
  const known = [...preset.options].some(o => o.value === s.template);
  if (document.activeElement !== preset) preset.value = known ? s.template : 'custom';
  const custom = preset.value === 'custom';
  $('#tplInput').hidden = !custom; $('#tplSave').hidden = !custom;
  if (document.activeElement !== $('#tplInput')) $('#tplInput').value = s.template || '';
  if (document.activeElement !== $('#proxyInput')) $('#proxyInput').value = s.proxy || '';
  $('#cookiesFilePath').textContent = s.cookies_file || 'Ninguno';
  $('#cookiesFilePath').title = s.cookies_file || '';
  $('#btnCookiesClear').hidden = !s.cookies_file;
  $('#btnCookiesFile').textContent = S.app.desktop ? 'Elegir archivo' : 'Subir archivo';
  const chromium = ['chrome', 'edge', 'brave', 'opera', 'vivaldi'].includes(s.cookies_browser);
  const note = $('#cookiesNote');
  note.hidden = !(chromium && S.app.platform === 'win32');
  note.textContent = 'En Windows, Chrome, Edge y similares cifran sus cookies y normalmente no se pueden leer. Usa Firefox o un archivo cookies.txt.';
  $$('.dest span').forEach(e => { e.textContent = short(s.folder); e.title = s.folder; });
  if ($('#pvExt')) $('#pvExt').textContent = extFor(s);
  if (S.preview && S.preview.type === 'video') paintChips();
}

let saveTimer;
function setOpt(key, value) {
  S.settings[key] = value; S.pending[key] = value;
  if (key === 'container' && value === 'webm' && S.settings.codec === 'h264') {
    S.settings.codec = S.pending.codec = 'vp9';
    toast('WEBM no admite H.264: se usará VP9');
  }
  syncControls();
  clearTimeout(saveTimer);
  saveTimer = setTimeout(flushSettings, 250);
}
async function flushSettings() {
  clearTimeout(saveTimer);
  const values = S.pending; S.pending = {};
  if (!Object.keys(values).length) return true;
  try {
    const r = await api('/api/settings', {values});
    S.settings = {...r.settings, ...S.pending};
    S.folder = r.folder;
    syncControls(); renderFolder();
    return true;
  } catch (e) {
    toast('No se pudo guardar el ajuste', 'err', e.message);
    try { const b = await api('/api/bootstrap'); S.settings = b.settings; S.folder = b.folder; syncControls(); renderFolder(); } catch {}
    return false;
  }
}
function currentOptions(extra = {}) {
  const keys = ['folder', 'mode', 'quality', 'container', 'codec', 'audio_format', 'audio_bitrate', 'subtitles', 'sub_langs', 'auto_subs', 'embed_subs', 'embed_thumbnail', 'embed_metadata', 'sponsorblock', 'template'];
  const options = {}; keys.forEach(k => options[k] = S.settings[k]);
  return Object.assign(options, extra);
}

function renderFolder() {
  const f = S.folder || {}, path = S.settings.folder || '';
  $$('[data-folder-path]').forEach(e => { e.textContent = path; e.title = path; });
  $$('[data-folder-free]').forEach(e => {
    e.hidden = f.free == null;
    e.textContent = f.free != null ? `${bytes(f.free)} libres` : '';
    e.classList.toggle('bad', f.free != null && f.free < 2 * 1024 ** 3);
    e.title = f.free != null && f.free < 2 * 1024 ** 3 ? 'Queda poco espacio en este disco' : 'Espacio libre en el disco de destino';
  });
  $$('[data-folder-cloud]').forEach(e => {
    e.hidden = !f.cloud; e.textContent = f.cloud || '';
    e.title = `Carpeta sincronizada con ${f.cloud}: lo que descargues se subirá a la nube y ocupará espacio en tu cuenta. Si no lo quieres, elige otra carpeta.`;
  });
  const messages = [];
  if (f.cloud) messages.push(`Esta carpeta está sincronizada con ${f.cloud}: lo que descargues se subirá a la nube.`);
  if (f.exists && !f.writable) messages.push('No hay permiso de escritura en esta carpeta.');
  const note = $('[data-folder-note]'); note.hidden = !messages.length; note.textContent = messages.join(' ');
  $$('.dest span').forEach(e => { e.textContent = short(path); e.title = path; });
}
async function refreshFolder() { try { S.folder = await api('/api/folder-info'); renderFolder(); } catch {} }
setInterval(refreshFolder, 60000);

async function pickFolder() {
  try {
    let path = '';
    if (window.pywebview && window.pywebview.api && window.pywebview.api.pick_folder) {
      path = await window.pywebview.api.pick_folder(S.settings.folder);
    } else {
      path = await openDialog({
        title: 'Carpeta de destino', body: 'Escribe la ruta completa de la carpeta.',
        html: `<input id="dlgPath" spellcheck="false" value="${esc(S.settings.folder)}">`,
        buttons: [{label: 'Cancelar', cls: 'ghost', value: '', cancel: true}, {label: 'Guardar', cls: 'primary', default: true, getValue: box => box.querySelector('#dlgPath').value.trim()}],
      });
    }
    if (path) {
      S.pending.folder = path; S.settings.folder = path;
      if (await flushSettings()) toast('Carpeta de destino actualizada', 'ok', path);
    }
  } catch (e) { toast(e.message, 'err'); }
}

async function pickCookiesFile() {
  try {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.pick_file) {
      const path = await window.pywebview.api.pick_file('');
      if (path) { S.pending.cookies_file = path; if (await flushSettings()) toast('Archivo de cookies guardado', 'ok'); }
      return;
    }
    // Servida desde un servidor, el archivo está en otra máquina: escribir su ruta no serviría de
    // nada, hay que subir el contenido.
    const input = $('#cookiesUpload');
    input.value = '';
    input.click();
  } catch (e) { toast(e.message, 'err'); }
}

function applySettings(r) {
  S.settings = {...r.settings, ...S.pending};
  S.folder = r.folder;
  syncControls(); renderFolder();
}

async function uploadCookiesFile(file) {
  if (!file) return;
  try {
    applySettings(await api('/api/cookies', {text: await file.text()}));
    toast('Archivo de cookies guardado', 'ok', file.name);
  } catch (e) { toast('No se pudo guardar el archivo de cookies', 'err', e.message); }
}

async function clearCookiesFile() {
  try {
    applySettings(await api('/api/cookies-clear', {}));
    toast('Archivo de cookies quitado');
  } catch (e) { toast('No se pudo quitar el archivo de cookies', 'err', e.message); }
}

/* ================= análisis y vista previa ================= */
async function analyze(query, playlist = false) {
  query = (query ?? $('#q').value).trim();
  if (!query) return $('#q').focus();
  const token = ++S.token;
  $('#preview').innerHTML = `<div class="card loading"><span class="spin"></span><div><b style="color:var(--text)">${isUrl(query) ? (playlist ? 'Cargando la playlist…' : 'Analizando el enlace…') : 'Buscando en YouTube…'}</b><div style="font-size:12.5px;margin-top:2px">${esc(query)}</div></div></div>`;
  $('#btnAnalyze').disabled = true;
  try {
    const data = await api('/api/info', {query, playlist});
    if (token !== S.token) return;
    if (data.type === 'search') S.lastSearch = data;
    S.preview = data;
    renderPreview();
  } catch (e) {
    if (token !== S.token) return;
    S.preview = null;
    $('#preview').innerHTML = `<div class="card errbox">${I.alert}<div><b>No se pudo analizar</b><small>${esc(e.message)}</small></div><button class="btn sm" data-pv="retry">Reintentar</button><button class="ibtn" data-pv="close" aria-label="Cerrar">${I.x}</button></div>`;
  } finally {
    if (token === S.token) $('#btnAnalyze').disabled = false;
  }
}
function closePreview() { S.token++; S.preview = null; $('#preview').innerHTML = ''; $('#btnAnalyze').disabled = false; }

function renderPreview() {
  const d = S.preview, pv = $('#preview');
  if (d.type === 'video') {
    const date = ymd(d.upload_date);
    const live = d.live_status === 'is_live' || d.live_status === 'is_upcoming';
    const back = S.lastSearch ? `<button class="linkbtn" data-pv="back">${I.back}Volver a los resultados</button>` : '';
    pv.innerHTML = `<div class="card pv">
      <div class="pv-media"><img src="${esc(d.thumbnail)}" referrerpolicy="no-referrer" alt="">${d.duration ? `<span class="badge-dur">${dur(d.duration)}</span>` : ''}${d.live_status === 'is_live' ? '<span class="badge-live">EN DIRECTO</span>' : d.live_status === 'is_upcoming' ? '<span class="badge-live">PRÓXIMAMENTE</span>' : ''}</div>
      <div class="pv-body">
        <div class="pv-head"><div>${back}<h2 title="${esc(d.title)}">${esc(d.title)}</h2>
          <div class="sub">${d.uploader ? `<span>${esc(d.uploader)}</span>` : ''}${d.view_count ? `<span>${views(d.view_count)}</span>` : ''}${date ? `<span>${date}</span>` : ''}${d.chapters ? `<span>${d.chapters} capítulos</span>` : ''}${d.subtitles && d.subtitles.length ? `<span>Subtítulos: ${esc(d.subtitles.slice(0, 6).join(', '))}${d.subtitles.length > 6 ? '…' : ''}</span>` : ''}</div></div>
          <button class="ibtn" data-pv="close" title="Cerrar (Esc)" aria-label="Cerrar vista previa">${I.x}</button></div>
        ${live ? `<div class="pv-note">${I.warn}<div>${d.live_status === 'is_live' ? 'Es un directo en curso. Podrás descargarlo cuando termine la emisión.' : 'Este estreno o directo todavía no ha empezado.'}</div></div>` : ''}
        <div class="lbl-s">Nombre del archivo</div>
        <div class="namefield" id="pvNameBox">${I.pen}<input id="pvName" spellcheck="false" autocomplete="off" aria-label="Nombre del archivo"><span class="ext" id="pvExt"></span><button class="ibtn" data-pv="resetname" id="pvReset" title="Volver al título original" aria-label="Volver al título original" hidden>${I.undo}</button></div>
        <div class="lbl-s">Elige calidad</div>
        <div class="qchips" id="qchips"></div>
        ${(d.audio_tracks || []).length > 1 ? `<div class="lbl-s">Pista de audio</div>
        <div class="pv-row"><label class="field"><span>Idioma</span><select id="pvTrack" aria-label="Pista de audio">
          ${d.audio_tracks.map(t => `<option value="${esc(t.value)}">${esc(t.label)}${t.original ? ' · original' : ''}</option>`).join('')}
        </select></label></div>` : ''}
        <div class="pv-row">
          <div class="trim">${I.cut}Recortar <input id="tStart" placeholder="inicio" title="Ejemplo: 1:30" aria-label="Inicio del recorte"> – <input id="tEnd" placeholder="${d.duration ? dur(d.duration) : 'fin'}" title="Ejemplo: 2:45" aria-label="Fin del recorte"></div>
          ${d.has_playlist ? `<button class="linkbtn" data-pv="playlist">${I.list}Cargar la playlist completa</button>` : ''}
        </div>
        <div class="pv-actions">
          <button class="btn primary lg" data-pv="add" ${live ? 'disabled' : ''}>${I.plus}Añadir a la cola</button>
          <button class="btn lg" data-pv="top" ${live ? 'disabled' : ''}>${I.top}Descargar primero</button>
          <span class="dest">${I.folder}<span></span></span>
        </div>
      </div></div>`;
    $('#pvName').value = d.title.replace(BAD_CHARS, '');
    paintChips();
  } else {
    const isSearch = d.type === 'search';
    const total = d.entries.reduce((a, e) => a + (e.duration || 0), 0);
    S.sel = new Set(isSearch ? [] : d.entries.map((e, i) => (/^\[(private|deleted)/i.test(e.title) || e.live) ? -1 : i).filter(i => i >= 0));
    pv.innerHTML = `<div class="card pl">
      <div class="pl-head"><div><div class="eyebrow">${isSearch ? 'Búsqueda' : 'Playlist'} · ${plural(d.entries.length, 'vídeo', 'vídeos')}${total ? ' · ' + longDur(total) : ''}</div><h2>${esc(d.title)}</h2>${d.uploader ? `<div class="sub">${esc(d.uploader)}</div>` : ''}</div>
        <button class="ibtn" data-pv="close" title="Cerrar (Esc)" aria-label="Cerrar">${I.x}</button></div>
      <div class="pl-tools">
        <label><input type="checkbox" class="cb" id="plAll"> Seleccionar todo</label>
        <input type="text" id="plFilter" placeholder="Filtrar por título…" aria-label="Filtrar por título">
        <span class="grow"></span>
        ${isSearch ? '' : `<label><label class="switch"><input type="checkbox" id="plSub" ${S.settings.playlist_subfolder ? 'checked' : ''} aria-label="Subcarpeta con el nombre de la playlist"><span></span></label>Subcarpeta con el nombre</label>`}
      </div>
      <div class="pl-list" id="plList">${d.entries.map((e, i) => `<label class="pl-row" data-i="${i}"><input type="checkbox" class="cb" data-i="${i}" aria-label="Seleccionar ${esc(e.title)}"><span class="idx">${i + 1}</span><img loading="lazy" referrerpolicy="no-referrer" src="${esc(e.thumbnail)}" alt=""><div class="t"><div title="${esc(e.title)}">${esc(e.title)}</div><small>${[e.uploader, dur(e.duration), e.live ? 'En directo' : ''].filter(Boolean).map(esc).join(' · ')}</small></div><button class="ibtn pen" data-ren1="${i}" title="Cambiar el nombre del archivo" aria-label="Cambiar el nombre del archivo">${I.pen}</button>${isSearch ? `<button class="btn sm" data-add1="${i}">${I.plus}Añadir</button><button class="btn sm ghost" data-open1="${i}" title="Ver detalles y calidades">Detalles</button>` : ''}</label>`).join('')}</div>
      <div class="pl-foot">
        <button class="btn primary" data-pv="addsel" id="plAdd"></button>
        <button class="btn" data-pv="topsel">${I.top}Descargar primero</button>
        <span class="dest">${I.folder}<span></span></span>
      </div></div>`;
    paintSelection();
  }
  syncControls();
}

function audioEstimate(d) {
  const s = S.settings, seconds = d.duration || 0;
  if (!seconds) return d.audio_size;
  if (['mp3', 'm4a', 'opus'].includes(s.audio_format)) return (+s.audio_bitrate || 192) * seconds * 125;
  if (s.audio_format === 'wav') return 192000 * seconds;
  if (s.audio_format === 'flac') return 105000 * seconds;
  return d.audio_size;
}
function paintChips() {
  const d = S.preview, s = S.settings, box = $('#qchips'); if (!box) return;
  const best = d.qualities[0];
  let html = `<button class="qchip ${s.mode === 'video' && s.quality === 'best' ? 'on' : ''}" data-q="best"><b>Máxima</b><small>${best ? best.label + (best.size ? ' · ~' + bytes(best.size) : '') : 'Automática'}</small></button>`;
  for (const q of d.qualities) {
    html += `<button class="qchip ${s.mode === 'video' && String(s.quality) === q.value ? 'on' : ''}" data-q="${esc(q.value)}"><b>${esc(q.label)}${q.hdr ? '<span class="hdr">HDR</span>' : ''}</b><small>${q.size ? '~' + bytes(q.size) : '—'}</small></button>`;
  }
  html += `<button class="qchip ${s.mode === 'audio' ? 'on' : ''}" data-q="audio"><b>Solo audio</b><small>${(s.audio_format || 'mp3').toUpperCase()} · ~${bytes(audioEstimate(d))}</small></button>`;
  box.innerHTML = html;
}
function paintSelection() {
  const d = S.preview; if (!d || !d.entries) return;
  $$('#plList input[data-i]').forEach(cb => { cb.checked = S.sel.has(+cb.dataset.i); cb.closest('.pl-row').classList.toggle('off', !cb.checked); });
  const n = S.sel.size;
  const visible = $$('#plList .pl-row').filter(r => !r.hidden);
  $('#plAll').checked = visible.length > 0 && visible.every(r => S.sel.has(+r.dataset.i));
  $('#plAdd').innerHTML = I.plus + (n ? `Añadir ${n} a la cola` : 'Selecciona vídeos');
  $('#plAdd').disabled = !n; $('[data-pv="topsel"]').disabled = !n;
}

async function addItems(items, top = false, subfolder = '', extra = {}) {
  if (!items.length) return null;
  try {
    const r = await api('/api/add', {items, options: currentOptions(extra), subfolder, top});
    if (!r.added && r.duplicates) toast(r.duplicates === 1 ? 'Ya está en la cola' : 'Todos ya estaban en la cola', 'info');
    else {
      toast(r.added === 1 ? 'Añadido a la cola' : `${r.added} vídeos añadidos a la cola`, 'ok',
        [top ? 'Se descargará a continuación' : (items.length === 1 ? (items[0].filename || items[0].title) : ''), r.duplicates ? `${plural(r.duplicates, 'ya estaba', 'ya estaban')} en la cola` : ''].filter(Boolean).join(' · '));
    }
    refreshSoon();
    return r;
  } catch (e) { toast('No se pudo añadir', 'err', e.message); return null; }
}
async function addUrls(text, top = false) {
  const urls = String(text).match(URL_RE) || [];
  if (!urls.length) { toast('No se encontraron enlaces', 'err'); return null; }
  try {
    const r = await api('/api/add-urls', {text, options: currentOptions(), top});
    toast(`${plural(r.added, 'enlace añadido', 'enlaces añadidos')} a la cola`, r.added ? 'ok' : 'info',
      [r.duplicates ? `${plural(r.duplicates, 'ya estaba', 'ya estaban')} en la cola` : '', 'Las playlists se expanden al empezar'].filter(Boolean).join(' · '));
    refreshSoon();
    return r;
  } catch (e) { toast('No se pudo añadir', 'err', e.message); return null; }
}

function handleIncoming(text) {
  text = String(text || '').trim(); if (!text) return;
  const urls = text.match(URL_RE) || [];
  ls.set('lastClip', urls[0] || text); $('#clipBanner').hidden = true;
  if (urls.length > 1) return addUrls(text);
  if (urls.length === 1) {
    if (S.settings.auto_add) { $('#q').value = ''; return addUrls(urls[0]); }
    $('#q').value = urls[0]; S.lastSearch = null;
    return analyze(urls[0]);
  }
  $('#q').value = text; $('#q').focus();
}

/* ================= historial ================= */
async function loadHistory() { try { S.history = (await api('/api/history')).history; renderHistory(); } catch {} }
function renderHistory() {
  const q = $('#hSearch').value.trim().toLowerCase();
  const rows = S.history.filter(h => !q || `${h.custom_name || ''} ${h.title} ${h.uploader || ''}`.toLowerCase().includes(q));
  $('#hCount').textContent = plural(S.history.length, 'descarga', 'descargas');
  $('#hList').innerHTML = rows.length ? rows.map(h => `<div class="hrow" data-hid="${esc(h.id)}">
      <img src="${esc(h.thumbnail)}" loading="lazy" referrerpolicy="no-referrer" alt="">
      <div class="t"><div title="${esc(h.custom_name ? h.custom_name + '\nOriginal: ' + h.title : h.title)}">${esc(h.custom_name || h.title)}${h.custom_name ? '<span class="cname">nombre propio</span>' : ''}</div><small><span class="chip">${esc(h.format_label || (h.mode || '').toUpperCase())}</span><span>${bytes(h.filesize)}</span>${h.uploader ? `<span>${esc(h.uploader)}</span>` : ''}<span>${ago(h.finished)}</span><span title="${esc(h.filepath)}">${esc(short(h.filepath))}</span></small></div>
      <div class="jact"><button class="ibtn" data-h="rename" title="Cambiar el nombre del archivo" aria-label="Cambiar el nombre del archivo">${I.pen}</button><button class="ibtn ok" data-h="play" title="Reproducir" aria-label="Reproducir">${I.play}</button><button class="ibtn" data-h="reveal" title="Mostrar en la carpeta" aria-label="Mostrar en la carpeta">${I.folder}</button><button class="ibtn" data-h="again" title="Volver a descargar con las opciones actuales" aria-label="Volver a descargar">${I.retry}</button><button class="ibtn" data-h="copy" title="Copiar enlace" aria-label="Copiar enlace">${I.copy}</button><button class="ibtn bad" data-h="remove" title="Quitar del historial" aria-label="Quitar del historial">${I.trash}</button></div>
    </div>`).join('') : `<div class="empty" style="border:0"><b>${q ? 'Sin resultados' : 'Todavía no hay descargas'}</b><p>${q ? 'Prueba con otro término.' : 'Aquí aparecerá todo lo que descargues.'}</p></div>`;
}

/* ================= motor, ajustes y acerca de ================= */
function renderEngine() {
  const c = S.components || {};
  const cell = (label, value, source) => `<div><span>${label}</span><b>${esc(value || 'No encontrado')}</b>${source ? `<small>${esc(source)}</small>` : ''}</div>`;
  $('#engineGrid').innerHTML = cell('yt-dlp', c.ytdlp, c.ytdlp_source) + cell('yt-dlp-ejs', c.ejs, '') + cell('FFmpeg', c.ffmpeg, c.ffmpeg_source)
    + cell('Motor JavaScript', c.js_runtime ? `${c.js_runtime} ${c.js_version || ''}` : '', c.js_source) + cell('Python', c.python, '');
  const issues = c.issues || [];
  $('#engineIssues').hidden = !issues.length;
  $('#engineIssues').innerHTML = issues.map(i => `<li>${esc(i)}</li>`).join('');
  renderUpdate();
}
function renderUpdate() {
  const u = (S.components || {}).update || {};
  $('#updateText').textContent = u.message || 'Comprueba si hay una versión nueva del motor de descargas.';
  $('#btnInstallUpdate').hidden = u.state !== 'available';
  $('#btnRestart').hidden = u.state !== 'restart' || !S.app.desktop;
  const busy = ['checking', 'installing'].includes(u.state);
  $('#btnCheckUpdate').disabled = busy;
  $('#btnCheckUpdate').textContent = u.state === 'installing' ? 'Instalando…' : u.state === 'checking' ? 'Buscando…' : 'Buscar actualizaciones';
  $('#updatePill').hidden = !['available', 'restart'].includes(u.state);
  $('#updatePillText').textContent = u.state === 'restart' ? 'Reinicia para usar el motor nuevo' : 'Actualización del motor disponible';
}
function renderAppUpdate() {
  const u = S.appUpdate || {};
  const available = u.state === 'available' && !!u.version;
  const dismissed = ls.get('hideAppUpdate', '') === u.version;
  $('#appUpdateBanner').hidden = !available || dismissed;
  $('#appUpdatePill').hidden = !available;
  if (available) {
    const weight = u.asset && u.asset.size ? ` · ${bytes(u.asset.size)}` : '';
    $('#appUpdateText').innerHTML = `<b>NactionX Downloader ${esc(u.version)}</b> ya está disponible <span>— tienes la ${esc(u.current || '')}${weight}</span>`;
    $('#appUpdatePillText').textContent = `Versión ${u.version} disponible`;
  }
  $('#appUpdateTitle').textContent = available ? `Versión ${u.version} disponible` : `Versión ${u.current || S.app.version || ''}`;
  $('#appUpdateDetail').textContent = u.message || '';
  const notes = $('#appUpdateNotes');
  notes.hidden = !(available && u.notes);
  notes.textContent = available ? (u.notes || '') : '';
  $('#btnAppUpdateDownload').hidden = !available;
  $('#btnAppUpdateCheck').disabled = u.state === 'checking';
  $('#btnAppUpdateCheck').textContent = u.state === 'checking' ? 'Buscando…' : 'Buscar ahora';
}
async function checkAppUpdate(silent) {
  S.appUpdate = {...S.appUpdate, state: 'checking', message: 'Buscando una versión nueva…'};
  renderAppUpdate();
  try {
    S.appUpdate = await api('/api/app/update-check', {});
    if (!silent) toast(S.appUpdate.message, S.appUpdate.state === 'error' ? 'err' : S.appUpdate.state === 'available' ? 'ok' : 'info');
  } catch (e) {
    S.appUpdate = {...S.appUpdate, state: 'error', message: e.message};
    if (!silent) toast(e.message, 'err');
  }
  renderAppUpdate();
}
async function pollAppUpdate(tries = 0) {
  try {
    S.appUpdate = await api('/api/app/update');
    renderAppUpdate();
    if (S.appUpdate.state === 'checking' && tries < 10) return setTimeout(() => pollAppUpdate(tries + 1), 3000);
    if (!$('#appUpdateBanner').hidden) toast(S.appUpdate.message, 'ok');
  } catch { /* sin conexión: se volverá a intentar al abrir la app */ }
}
async function downloadAppUpdate() {
  try {
    await api('/api/app/update-download', {});
    toast('Se ha abierto la descarga en tu navegador', 'ok');
  } catch (e) { toast(e.message, 'err'); }
}
function renderIssues() {
  const issues = (S.components || {}).issues || [];
  $('#issuesBanner').hidden = !issues.length;
  $('#issuesText').textContent = issues.join(' ');
}
function renderAbout() {
  $('#shortcutsRow').hidden = !(S.app.portable && S.app.platform === 'win32');
  $('#aboutVersion').textContent = `versión ${S.app.version}`;
  $('#aboutData').textContent = `Datos de la app: ${S.app.data_dir}`;
  const rows = [
    ['Pegar enlace y analizar', `<kbd>${MOD}</kbd> <kbd>V</kbd>`], ['Analizar o buscar', '<kbd>Enter</kbd>'],
    ['Añadir en lote', `<kbd>${MOD}</kbd> <kbd>B</kbd>`], ['Ir a la barra de enlaces', `<kbd>${MOD}</kbd> <kbd>L</kbd>`],
    ['Cerrar vista previa o diálogo', '<kbd>Esc</kbd>'], ['Reproducir una completada', 'Doble clic'],
  ];
  $('#shortcuts').innerHTML = rows.map(([label, keys]) => `<div>${label} <span>${keys}</span></div>`).join('');
  $('#pasteKbd').textContent = `${MOD} V`;
}
async function checkUpdates(silent) {
  try {
    const u = await api('/api/components/check', {});
    S.components.update = u; renderUpdate();
    if (!silent) toast(u.message, u.state === 'error' ? 'err' : 'info');
  } catch (e) { if (!silent) toast(e.message, 'err'); }
}
async function installUpdate() {
  try {
    await api('/api/components/update', {});
    S.components.update = {state: 'installing', message: 'Descargando la nueva versión del motor…'};
    renderUpdate();
    const tick = async () => {
      try {
        const c = await api('/api/components');
        S.components = c; renderEngine();
        if (c.update.state === 'installing') return setTimeout(tick, 1500);
        toast(c.update.message, c.update.state === 'error' ? 'err' : 'ok');
      } catch { setTimeout(tick, 3000); }
    };
    setTimeout(tick, 1500);
  } catch (e) { toast(e.message, 'err'); }
}
async function restartApp() {
  const active = S.jobs.filter(j => ACTIVE.includes(j.status)).length;
  if (active && !(await ask('Reiniciar la app', `Hay ${plural(active, 'descarga activa', 'descargas activas')}. Se pausarán y continuarán solas al volver a abrir.`, 'Reiniciar'))) return;
  try { await api('/api/app/restart', {}); } catch (e) { toast(e.message, 'err'); }
}

/* ================= vistas ================= */
function setView(view) {
  S.view = view; ls.set('view', view);
  $$('#nav button').forEach(b => { b.classList.toggle('active', b.dataset.view === view); b.setAttribute('aria-current', b.dataset.view === view ? 'page' : 'false'); });
  ['downloads', 'history', 'settings'].forEach(x => $('#view-' + x).hidden = x !== view);
  if (view === 'history') loadHistory();
  if (view === 'settings') refreshFolder();
  $('#main').scrollTop = 0;
}

/* ================= eventos ================= */
$('#nav').addEventListener('click', e => { const b = e.target.closest('button[data-view]'); if (b) setView(b.dataset.view); });
document.addEventListener('click', e => {
  const goto = e.target.closest('[data-goto]'); if (goto) setView(goto.dataset.goto);
  if (e.target.closest('[data-pick]')) pickFolder();
  if (e.target.closest('[data-openfolder]')) api('/api/open', {path: S.settings.folder, mode: 'folder'}).catch(err => toast(err.message, 'err'));
});
$('#updatePill').addEventListener('click', () => setView('settings'));
$('#appUpdatePill').addEventListener('click', () => setView('settings'));
$('#btnAppUpdateGet').addEventListener('click', downloadAppUpdate);
$('#btnAppUpdateDownload').addEventListener('click', downloadAppUpdate);
$('#btnAppUpdateCheck').addEventListener('click', () => checkAppUpdate(false));
$('#btnAppUpdateHide').addEventListener('click', () => { ls.set('hideAppUpdate', S.appUpdate.version || ''); renderAppUpdate(); });
$('#btnAnalyze').addEventListener('click', () => { S.lastSearch = null; analyze(); });
$('#q').addEventListener('keydown', e => { if (e.key === 'Enter') { S.lastSearch = null; analyze(); } });
$('#q').addEventListener('input', () => { const v = $('#q').value.trim(); $('#btnAnalyze').textContent = !v || isUrl(v) ? 'Analizar' : 'Buscar'; });
$('#q').addEventListener('paste', e => {
  const text = (e.clipboardData.getData('text') || '').trim();
  if ((text.match(URL_RE) || []).length) { e.preventDefault(); handleIncoming(text); }
});
document.addEventListener('paste', e => {
  if (e.target.closest('input,textarea,select')) return;
  const text = e.clipboardData.getData('text');
  if (text) { e.preventDefault(); setView('downloads'); handleIncoming(text); }
});
document.addEventListener('keydown', e => {
  if (!$('#dialog').hidden) return;
  const mod = e.ctrlKey || e.metaKey;
  if (e.key === 'Escape') { if (!$('#batch').hidden) return closeBatch(); if (S.preview || $('#preview').innerHTML) closePreview(); }
  if (mod && e.key.toLowerCase() === 'b') { e.preventDefault(); openBatch(); }
  if (mod && e.key.toLowerCase() === 'l') { e.preventDefault(); setView('downloads'); $('#q').focus(); $('#q').select(); }
});

$('#modeSeg').addEventListener('click', e => { const b = e.target.closest('button'); if (b) setOpt('mode', b.dataset.mode); });
document.addEventListener('change', e => {
  const el = e.target.closest('[data-key]'); if (!el) return;
  let value = el.type === 'checkbox' ? el.checked : el.value;
  if (el.dataset.key === 'concurrency') value = +value;
  setOpt(el.dataset.key, value);
});
$('#tplPreset').addEventListener('change', e => {
  if (e.target.value === 'custom') { $('#tplInput').hidden = false; $('#tplSave').hidden = false; $('#tplInput').focus(); }
  else setOpt('template', e.target.value);
});
$('#tplSave').addEventListener('click', async () => { S.pending.template = $('#tplInput').value.trim(); if (await flushSettings()) toast('Plantilla guardada', 'ok'); });
$('#tplInput').addEventListener('keydown', e => { if (e.key === 'Enter') $('#tplSave').click(); });
$('#btnAdv').addEventListener('click', () => { const adv = $('#adv'); adv.hidden = !adv.hidden; ls.set('adv', !adv.hidden); $('#btnAdv').classList.toggle('on', !adv.hidden); $('#btnAdv').setAttribute('aria-expanded', String(!adv.hidden)); });
$('#btnProxySave').addEventListener('click', async () => { S.pending.proxy = $('#proxyInput').value.trim(); if (await flushSettings()) toast(S.settings.proxy ? 'Proxy guardado' : 'Proxy desactivado', 'ok'); });
$('#btnCookiesFile').addEventListener('click', pickCookiesFile);
$('#cookiesUpload').addEventListener('change', e => uploadCookiesFile(e.target.files[0]));
$('#btnCookiesClear').addEventListener('click', clearCookiesFile);
$('#btnCheckUpdate').addEventListener('click', () => checkUpdates(false));
$('#btnInstallUpdate').addEventListener('click', installUpdate);
$('#btnRestart').addEventListener('click', restartApp);
$('#btnShortcuts').addEventListener('click', async () => {
  try { const r = await api('/api/app/shortcuts', {}); toast('Accesos directos creados', 'ok', `${r.links.length} accesos: escritorio y menú Inicio`); }
  catch (e) { toast('No se pudieron crear los accesos directos', 'err', e.message); }
});
$('#btnOpenLogs').addEventListener('click',() => api('/api/open', {mode: 'logs'}).catch(e => toast(e.message, 'err')));
$('#btnNotices').addEventListener('click', () => api('/api/open', {mode: 'notices'}).catch(e => toast(e.message, 'err')));

/* vista previa */
$('#preview').addEventListener('click', async e => {
  const d = S.preview;
  const chip = e.target.closest('[data-q]');
  if (chip) {
    if (chip.dataset.q === 'audio') setOpt('mode', 'audio');
    else { S.settings.mode = S.pending.mode = 'video'; setOpt('quality', chip.dataset.q); }
    return;
  }
  const add1 = e.target.closest('[data-add1]');
  if (add1) { e.preventDefault(); const item = d.entries[+add1.dataset.add1]; add1.disabled = true; add1.innerHTML = I.check + 'Añadido'; return addItems([item]); }
  const rename1 = e.target.closest('[data-ren1]');
  if (rename1) {
    e.preventDefault();
    const item = d.entries[+rename1.dataset.ren1], box = rename1.closest('.pl-row').querySelector('.t div');
    const paint = () => { box.innerHTML = esc(item.filename || item.title) + (item.filename ? '<span class="cname">nombre propio</span>' : ''); box.title = item.filename ? `${item.filename}\nOriginal: ${item.title}` : item.title; };
    return inlineEdit(box, item.filename || item.title.replace(BAD_CHARS, ''), extFor(), async v => { item.filename = v === item.title.replace(BAD_CHARS, '') ? '' : v; }, paint);
  }
  const open1 = e.target.closest('[data-open1]');
  if (open1) { e.preventDefault(); const item = d.entries[+open1.dataset.open1]; return analyze(item.url); }
  const b = e.target.closest('[data-pv]'); if (!b) return;
  const act = b.dataset.pv;
  if (act === 'close') { S.lastSearch = null; return closePreview(); }
  if (act === 'back') { S.preview = S.lastSearch; return renderPreview(); }
  if (act === 'retry') return analyze();
  if (act === 'resetname') { $('#pvName').value = d.title.replace(BAD_CHARS, ''); $('#pvName').dispatchEvent(new Event('input', {bubbles: true})); return $('#pvName').focus(); }
  if (act === 'playlist') return analyze($('#q').value || d.url, true);
  if (act === 'add' || act === 'top') {
    const name = $('#pvName').value.trim();
    const filename = name && name !== d.title.replace(BAD_CHARS, '') ? name : '';
    const track = $('#pvTrack');
    // Solo se manda si el usuario ha cambiado la pista: la primera de la lista es la original.
    const audio_track = track && track.selectedIndex > 0 ? track.value : '';
    const r = await addItems([{url: d.url, title: d.title, thumbnail: d.thumbnail, uploader: d.uploader, duration: d.duration, filename}], act === 'top', '', {start: $('#tStart').value.trim(), end: $('#tEnd').value.trim(), audio_track});
    if (r && r.added) { if (S.lastSearch) { S.preview = S.lastSearch; renderPreview(); } else { closePreview(); $('#q').value = ''; } }
  }
  if (act === 'addsel' || act === 'topsel') {
    const items = d.entries.filter((_, i) => S.sel.has(i));
    const subfolder = d.type === 'playlist' && $('#plSub') && $('#plSub').checked ? d.title : '';
    const r = await addItems(items, act === 'topsel', subfolder);
    if (r && (r.added || r.duplicates)) { S.lastSearch = null; closePreview(); $('#q').value = ''; }
  }
});
$('#preview').addEventListener('change', e => {
  if (e.target.id === 'plAll') {
    $$('#plList .pl-row').filter(r => !r.hidden).forEach(r => e.target.checked ? S.sel.add(+r.dataset.i) : S.sel.delete(+r.dataset.i));
    return paintSelection();
  }
  const cb = e.target.closest('#plList input[data-i]');
  if (cb) { cb.checked ? S.sel.add(+cb.dataset.i) : S.sel.delete(+cb.dataset.i); paintSelection(); }
});
$('#preview').addEventListener('input', e => {
  if (e.target.id === 'pvName') {
    const input = e.target;
    if (BAD_TEST.test(input.value)) { const p = Math.max(0, input.selectionStart - 1); input.value = input.value.replace(BAD_CHARS, ''); input.setSelectionRange(p, p); }
    const custom = input.value.trim() !== S.preview.title.replace(BAD_CHARS, '');
    $('#pvNameBox').classList.toggle('custom', custom); $('#pvReset').hidden = !custom;
    return;
  }
  if (e.target.id !== 'plFilter') return;
  const q = e.target.value.toLowerCase();
  $$('#plList .pl-row').forEach(r => r.hidden = q && !S.preview.entries[+r.dataset.i].title.toLowerCase().includes(q));
  paintSelection();
});

/* cola */
$('#qTabs').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; S.filter = b.dataset.f; $$('#qTabs button').forEach(x => { x.classList.toggle('on', x === b); x.setAttribute('aria-selected', String(x === b)); }); renderQueue(); });
$('#qList').addEventListener('click', e => { const b = e.target.closest('[data-act]'); if (!b) return; jobAct(b.closest('.job').dataset.id, b.dataset.act); });
$('#qList').addEventListener('dblclick', e => { const el = e.target.closest('.job.st-done'); if (el && !el.dataset.editing && !e.target.closest('button,input')) jobAct(el.dataset.id, 'play'); });
$('#btnPauseAll').addEventListener('click', async () => { try { await api('/api/queue', {action: S.paused ? 'resume_all' : 'pause_all'}); refreshSoon(); } catch (e) { toast(e.message, 'err'); } });
$('#btnRetryFailed').addEventListener('click', async () => { await api('/api/queue', {action: 'retry_failed'}); refreshSoon(); });
$('#btnClearDone').addEventListener('click', async () => { await api('/api/queue', {action: 'clear_done'}); refreshSoon(); });
$('#btnCancelAll').addEventListener('click', async () => {
  const pending = S.jobs.filter(j => ACTIVE.includes(j.status) || ['queued', 'paused'].includes(j.status)).length;
  if (!pending) return toast('No hay descargas pendientes');
  if (await ask('Cancelar todo', `Se cancelarán ${plural(pending, 'descarga', 'descargas')} y se borrará lo descargado parcialmente.`, 'Cancelar todo', true)) {
    await api('/api/queue', {action: 'cancel_all'}); refreshSoon();
  }
});

/* arrastrar para reordenar */
const qList = $('#qList');
qList.addEventListener('dragstart', e => {
  const el = e.target.closest('.job'); if (!el || el.dataset.editing) return;
  S.dragging = el; el.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/x-job', el.dataset.id);
});
qList.addEventListener('dragover', e => {
  if (!S.dragging) return; e.preventDefault();
  const after = [...qList.querySelectorAll('.job:not(.dragging)')].find(c => { const r = c.getBoundingClientRect(); return e.clientY < r.top + r.height / 2; });
  if (after) qList.insertBefore(S.dragging, after); else qList.appendChild(S.dragging);
});
qList.addEventListener('dragend', async () => {
  const el = S.dragging; if (!el) return; el.classList.remove('dragging');
  const visibleIds = [...qList.children].map(c => c.dataset.id);
  const visibleSet = new Set(visibleIds); let k = 0;
  const order = S.jobs.map(j => visibleSet.has(j.id) ? visibleIds[k++] : j.id);
  S.jobs.sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
  S.dragging = null;
  try { await api('/api/reorder', {ids: order}); } catch (e) { toast(e.message, 'err'); }
  refreshSoon();
});

/* soltar enlaces en la ventana */
let dragDepth = 0;
window.addEventListener('dragenter', e => { if (S.dragging) return; if ([...e.dataTransfer.types].some(t => t === 'text/uri-list' || t === 'text/plain')) { dragDepth++; $('#dropzone').hidden = false; } });
window.addEventListener('dragleave', () => { if (S.dragging) return; dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) $('#dropzone').hidden = true; });
window.addEventListener('dragover', e => { if (!S.dragging) e.preventDefault(); });
window.addEventListener('drop', e => {
  if (S.dragging) return; e.preventDefault(); dragDepth = 0; $('#dropzone').hidden = true;
  const text = e.dataTransfer.getData('text/uri-list') || e.dataTransfer.getData('text/plain');
  if (text) { setView('downloads'); handleIncoming(text.split(/\r?\n/).filter(l => !l.startsWith('#')).join('\n')); }
});

/* portapapeles */
async function checkClipboard() {
  if (!S.settings.clipboard || S.view !== 'downloads' || document.hidden) return;
  try {
    const {urls} = await api('/api/clipboard');
    const url = (urls || []).find(u => SITE_RE.test(u));
    if (!url || url === ls.get('lastClip', '')) return;
    if (S.jobs.some(j => j.url === url) || $('#q').value.trim() === url) return;
    S.clip = url; $('#clipUrl').textContent = url; $('#clipBanner').hidden = false;
  } catch {}
}
window.addEventListener('focus', () => setTimeout(checkClipboard, 150));
document.addEventListener('visibilitychange', () => { if (!document.hidden) setTimeout(checkClipboard, 150); });
$('#clipClose').addEventListener('click', () => { ls.set('lastClip', S.clip); $('#clipBanner').hidden = true; });
$('#clipAnalyze').addEventListener('click', () => { ls.set('lastClip', S.clip); $('#clipBanner').hidden = true; $('#q').value = S.clip; S.lastSearch = null; analyze(S.clip); });
$('#clipAdd').addEventListener('click', () => { ls.set('lastClip', S.clip); $('#clipBanner').hidden = true; addUrls(S.clip); });

/* lote */
function openBatch() { setView('downloads'); $('#batch').hidden = false; $('#batchText').focus(); countBatch(); }
function closeBatch() { $('#batch').hidden = true; }
function countBatch() { const n = new Set($('#batchText').value.match(URL_RE) || []).size; $('#batchCount').textContent = plural(n, 'enlace detectado', 'enlaces detectados'); $('#batchGo').disabled = $('#batchTop').disabled = !n; }
$('#btnBatch').addEventListener('click', openBatch);
$('#batchCancel').addEventListener('click', closeBatch);
$('#batch').addEventListener('mousedown', e => { if (e.target.id === 'batch') closeBatch(); });
$('#batchText').addEventListener('input', countBatch);
$('#batchGo').addEventListener('click', async () => { if (await addUrls($('#batchText').value)) { $('#batchText').value = ''; closeBatch(); } });
$('#batchTop').addEventListener('click', async () => { if (await addUrls($('#batchText').value, true)) { $('#batchText').value = ''; closeBatch(); } });

/* historial */
$('#hSearch').addEventListener('input', renderHistory);
$('#btnClearHistory').addEventListener('click', async () => {
  if (await ask('Borrar historial', 'Se borrará la lista del historial. Los archivos descargados no se tocan.', 'Borrar', true)) {
    await api('/api/history', {action: 'clear'}); loadHistory();
  }
});
$('#hList').addEventListener('click', async e => {
  const b = e.target.closest('[data-h]'); if (!b) return;
  const h = S.history.find(x => x.id === b.closest('.hrow').dataset.hid); if (!h) return;
  if (b.dataset.h === 'rename') {
    return inlineEdit(b.closest('.hrow').querySelector('.t div'), fileBase(h.filepath) || h.title, fileExt(h.filepath), v => renameApi(h.id, v), () => { loadHistory(); refreshSoon(); });
  }
  try {
    if (b.dataset.h === 'play') await api('/api/open', {path: h.filepath, mode: 'file'});
    if (b.dataset.h === 'reveal') await api('/api/open', {path: h.filepath, mode: 'reveal'});
    if (b.dataset.h === 'again') await addItems([{url: h.url, title: h.title, thumbnail: h.thumbnail, uploader: h.uploader, duration: h.duration}]);
    if (b.dataset.h === 'copy') { await copyText(h.url); ls.set('lastClip', h.url); toast('Enlace copiado'); }
    if (b.dataset.h === 'remove') { await api('/api/history', {action: 'remove', id: h.id}); loadHistory(); }
  } catch (err) { toast(err.message, 'err'); }
});

/* ================= inicio ================= */
(async function init() {
  if (ls.get('adv', false)) { $('#adv').hidden = false; $('#btnAdv').classList.add('on'); $('#btnAdv').setAttribute('aria-expanded', 'true'); }
  setView(ls.get('view', 'downloads'));
  renderEmpty(0);
  for (let attempt = 0; ; attempt++) {
    try { await bootstrap(); setConn(true); break; } catch (e) {
      setConn(false);
      if (e.status === 401 || e.status === 403) { $('#offline').textContent = 'Sesión no válida: abre la app desde su acceso directo.'; $('#offline').hidden = false; return; }
      await sleep(Math.min(5000, 500 * (attempt + 1)));
    }
  }
  poll();
  setTimeout(checkClipboard, 800);
})();
