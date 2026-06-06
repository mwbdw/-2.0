// ── State ────────────────────────────────────────────────────────────────────
let friends = [];
let messages = [];
let sseSource = null;

// ── Init ─────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  loadConfig();
  fetchStatus();
  connectLogs();
  let _pollTimer = setInterval(fetchStatus, 3000);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      clearInterval(_pollTimer);
    } else {
      fetchStatus();
      _pollTimer = setInterval(fetchStatus, 3000);
    }
  });
});

// ── Config ───────────────────────────────────────────────────────────────────
async function loadConfig() {
  const cfg = await api('GET', '/api/config');
  friends = cfg.friends || [];
  messages = cfg.messages || [];
  const t = cfg.send_time || '08:00';
  const el = document.getElementById('sched-time');
  if (el) el.value = t;
  document.getElementById('headless').checked = !!cfg.headless;
  renderTags('friends-tags', friends, removeFriend);
  renderTags('messages-tags', messages, removeMessage);
}

async function saveConfig() {
  const cfg = {
    friends,
    messages,
    send_time: document.getElementById('sched-time').value,
    headless: document.getElementById('headless').checked,
  };
  await api('PUT', '/api/config', cfg);
  toast('配置已保存 ✓');
}

// ── Friends / Messages tags ───────────────────────────────────────────────────
function addFriend() {
  const input = document.getElementById('friend-input');
  const val = input.value.trim();
  if (!val || friends.includes(val)) { input.value = ''; return; }
  friends.push(val);
  input.value = '';
  renderTags('friends-tags', friends, removeFriend);
}

function removeFriend(name) {
  friends = friends.filter(f => f !== name);
  renderTags('friends-tags', friends, removeFriend);
}

function addMessage() {
  const input = document.getElementById('msg-input');
  const val = input.value.trim();
  if (!val || messages.includes(val)) { input.value = ''; return; }
  messages.push(val);
  input.value = '';
  renderTags('messages-tags', messages, removeMessage);
}

function removeMessage(msg) {
  messages = messages.filter(m => m !== msg);
  renderTags('messages-tags', messages, removeMessage);
}

function renderTags(containerId, items, onRemove) {
  const box = document.getElementById(containerId);
  box.innerHTML = '';
  items.forEach(item => {
    const tag = document.createElement('span');
    tag.className = 'tag';
    const btn = document.createElement('button');
    btn.className = 'tag-del';
    btn.title = '删除';
    btn.textContent = '×';
    btn.addEventListener('click', () => onRemove(item));
    tag.appendChild(document.createTextNode(item));
    tag.appendChild(btn);
    box.appendChild(tag);
  });
}

function _schedTimeEl() {
  return document.getElementById('sched-time');
}

// ── Status ────────────────────────────────────────────────────────────────────
async function fetchStatus() {
  try {
    const s = await api('GET', '/api/status');
    const badge = document.getElementById('run-badge');
    badge.textContent = s.running ? '运行中' : '空闲';
    badge.className = 'badge ' + (s.running ? 'running' : 'idle');

    setStatValue('stat-login', s.login ? '已登录 ✓' : '未登录', s.login ? 'ok' : 'warn');
    setStatValue('stat-sched', s.scheduled ? '已启动 ✓' : '未启动', s.scheduled ? 'ok' : 'off');
    setStatValue('stat-last', s.last_run || '—', s.last_run ? '' : 'off');
    setStatValue('stat-next', s.next_run || '—', s.next_run ? '' : 'off');

    document.getElementById('btn-run').disabled = s.running;
    document.getElementById('btn-login').disabled = s.running;
    document.getElementById('btn-sched-start').disabled = s.scheduled || s.running;
    document.getElementById('btn-sched-stop').disabled = !s.scheduled;
  } catch (_) {}
}

function setStatValue(id, text, cls) {
  const el = document.getElementById(id);
  el.textContent = text;
  el.className = 'stat-value ' + (cls || '');
}

// ── Actions ───────────────────────────────────────────────────────────────────
async function runNow() {
  try {
    await api('POST', '/api/run');
    toast('任务已启动');
    fetchStatus();
  } catch (e) {
    toast(e.message, true);
  }
}

async function startSchedule() {
  try {
    const el = _schedTimeEl();
    const send_time = el ? el.value : '08:00';
    await api('POST', '/api/schedule', { action: 'start', send_time });
    toast(`定时任务已启动（${send_time}）`);
    fetchStatus();
  } catch (e) {
    toast(e.message, true);
  }
}

async function applyScheduleTime() {
  try {
    const el = _schedTimeEl();
    const send_time = el ? el.value : '';
    if (!send_time) { toast('请先选择时间', true); return; }
    await api('POST', '/api/schedule', { action: 'update_time', send_time });
    toast(`定时时间已更新为 ${send_time}`);
    fetchStatus();
  } catch (e) {
    toast(e.message, true);
  }
}

async function stopSchedule() {
  await api('POST', '/api/schedule', { action: 'stop' });
  toast('定时任务已停止');
  fetchStatus();
}

async function doLogin() {
  try {
    await api('POST', '/api/login');
    toast('浏览器已打开，请扫码登录');
    fetchStatus();
  } catch (e) {
    toast(e.message, true);
  }
}

async function clearCookies() {
  await api('DELETE', '/api/cookies');
  toast('登录状态已清除');
  fetchStatus();
}

async function resetState() {
  await api('POST', '/api/reset');
  toast('运行状态已重置 ✓');
  fetchStatus();
}

// ── Logs via SSE ─────────────────────────────────────────────────────────────
function connectLogs() {
  if (sseSource) sseSource.close();
  sseSource = new EventSource('/api/logs');
  sseSource.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    appendLog(msg);
  };
  sseSource.onerror = () => {
    // Reconnect after 3s on error
    sseSource.close();
    setTimeout(connectLogs, 3000);
  };
}

function appendLog(msg) {
  const box = document.getElementById('log-box');
  const line = document.createElement('div');
  let cls = '';
  if (msg.includes('[✓]') || msg.includes('成功')) cls = 'ok';
  else if (msg.includes('[✗]') || msg.includes('失败') || msg.includes('错误')) cls = 'err';
  else if (msg.includes('[~]') || msg.includes('[!]')) cls = 'dim';
  line.className = 'log-line' + (cls ? ' ' + cls : '');

  const ts = document.createElement('span');
  ts.className = 'log-ts';
  const now = new Date();
  ts.textContent = now.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });

  const text = document.createElement('span');
  text.className = 'log-msg';
  text.textContent = msg;

  line.appendChild(ts);
  line.appendChild(text);
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
}

function clearLogs() {
  document.getElementById('log-box').innerHTML = '';
}

// ── API helper ────────────────────────────────────────────────────────────────
async function api(method, url, body) {
  const opts = {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
  };
  if (body) opts.body = JSON.stringify(body);
  const res = await fetch(url, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

// ── Toast ─────────────────────────────────────────────────────────────────────
let _toastTimer = null;
function toast(msg, isError = false) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.classList.toggle('error', isError);
  el.classList.add('show');
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), 2800);
}
