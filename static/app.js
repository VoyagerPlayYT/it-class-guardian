// IT-Class Guardian // Teacher Dashboard Client Logic

let stationsData = [];
let activeViewingStationId = null;
let ws = null;

// DOM Elements
const stationsGrid = document.getElementById('stationsGrid');
const metricOnlineCount = document.getElementById('metricOnlineCount');
const metricDiskAlerts = document.getElementById('metricDiskAlerts');
const metricGameAlerts = document.getElementById('metricGameAlerts');
const stationsGridHeader = document.getElementById('stationsGridHeader');
const stationSearchInput = document.getElementById('stationSearchInput');
const btnRefreshGrid = document.getElementById('btnRefreshGrid');
const logsTableBody = document.getElementById('logsTableBody');

// Ribbon buttons
const btnBroadcastRollback = document.getElementById('btnBroadcastRollback');
const btnBroadcastSnapshot = document.getElementById('btnBroadcastSnapshot');
const btnBroadcastLock = document.getElementById('btnBroadcastLock');
const btnBroadcastUnlock = document.getElementById('btnBroadcastUnlock');
const btnBroadcastPurge = document.getElementById('btnBroadcastPurge');
const btnBroadcastReboot = document.getElementById('btnBroadcastReboot');
const btnOpenAssignmentModal = document.getElementById('btnOpenAssignmentModal');

// Modals
const screenshotModal = document.getElementById('screenshotModal');
const screenshotContainer = document.getElementById('screenshotContainer');
const screenshotModalTitle = document.getElementById('screenshotModalTitle');
const btnCloseScreenshotModal = document.getElementById('btnCloseScreenshotModal');
const btnCloseScreenshotModalBtn = document.getElementById('btnCloseScreenshotModalBtn');
const btnRefreshScreenshot = document.getElementById('btnRefreshScreenshot');

const assignmentModal = document.getElementById('assignmentModal');
const assignmentForm = document.getElementById('assignmentForm');
const btnCloseAssignmentModal = document.getElementById('btnCloseAssignmentModal');
const btnCancelAssignment = document.getElementById('btnCancelAssignment');

// Toast notifications
function showToast(message, type = 'success') {
  const hub = document.getElementById('toastHub');
  const t = document.createElement('div');
  t.className = `toast ${type}`;
  t.textContent = message;
  hub.appendChild(t);
  setTimeout(() => {
    t.style.opacity = '0';
    setTimeout(() => t.remove(), 300);
  }, 4000);
}

// Format date
function formatTime(ts) {
  if (!ts) return '-';
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

// Connect WebSocket
function connectWebSocket() {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${proto}//${window.location.host}/ws/classroom`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    document.getElementById('serverStatusBadge').textContent = '🟢 В СЕТИ [8023]';
    document.getElementById('serverStatusBadge').className = 'm-val val-green';
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === 'STATIONS_UPDATE') {
        stationsData = msg.stations;
        renderStations();
        updateTopMetrics();
      }
    } catch (err) {
      console.error('WS parse error:', err);
    }
  };

  ws.onclose = () => {
    document.getElementById('serverStatusBadge').textContent = '🔴 СВЯЗЬ ПРЕРВАНА';
    document.getElementById('serverStatusBadge').className = 'm-val val-crimson';
    setTimeout(connectWebSocket, 2000);
  };
}

// Fetch Stations fallback
async function fetchStations() {
  try {
    const res = await fetch('/api/stations');
    const data = await res.json();
    stationsData = data.stations || [];
    renderStations();
    updateTopMetrics();
  } catch (err) {
    console.error('Failed to fetch stations:', err);
  }
}

// Fetch Audit Logs
async function fetchLogs() {
  try {
    const res = await fetch('/api/logs?limit=25');
    const data = await res.json();
    renderLogs(data.logs || []);
  } catch (err) {
    console.error('Failed to fetch logs:', err);
  }
}

function renderLogs(logs) {
  if (!logsTableBody) return;
  logsTableBody.innerHTML = '';
  if (logs.length === 0) {
    logsTableBody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:#60606A; padding:15px;">Журнал пуст</td></tr>';
    return;
  }

  logs.forEach(log => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td style="color:#A1A1AA;">${formatTime(log.created_at)}</td>
      <td><span style="color:#38BDF8; font-weight:600;">${escapeHtml(log.event_type)}</span></td>
      <td>${escapeHtml(log.station_name || log.station_id)}</td>
      <td style="color:#E4E4E7;">${escapeHtml(log.details)}</td>
    `;
    logsTableBody.appendChild(tr);
  });
}

function updateTopMetrics() {
  const total = stationsData.length;
  const online = stationsData.filter(s => s.is_online).length;
  const diskAlerts = stationsData.filter(s => s.disk_alert).length;
  const gameAlerts = stationsData.filter(s => s.game_detected).length;

  metricOnlineCount.textContent = `${online} / ${total}`;
  metricDiskAlerts.textContent = diskAlerts.toString();
  metricGameAlerts.textContent = gameAlerts.toString();
  stationsGridHeader.textContent = `Всего рабочих мест: ${total} • Активно: ${online}`;
}

function renderStations() {
  const query = stationSearchInput.value.toLowerCase().trim();
  stationsGrid.innerHTML = '';

  const filtered = stationsData.filter(s => {
    if (!query) return true;
    return (
      s.station_name.toLowerCase().includes(query) ||
      (s.username && s.username.toLowerCase().includes(query)) ||
      (s.active_window && s.active_window.toLowerCase().includes(query)) ||
      (s.ip_address && s.ip_address.includes(query))
    );
  });

  if (filtered.length === 0) {
    stationsGrid.innerHTML = '<div style="grid-column: 1/-1; padding: 30px; text-align: center; color: #8E8E98;">Компьютеры учеников не найдены</div>';
    return;
  }

  filtered.forEach(s => {
    const card = document.createElement('div');
    let alertClass = '';
    if (s.game_detected) alertClass = 'alert-game';
    else if (s.disk_alert) alertClass = 'alert-disk';

    card.className = `station-card ${alertClass}`;

    let badgeClass = s.is_online ? 'badge-online' : 'badge-offline';
    let badgeText = s.is_online ? 'ОНЛАЙН' : 'ОФЛАЙН';
    if (s.is_locked) {
      badgeClass = 'badge-locked';
      badgeText = '🔒 БЛОК';
    }

    const cpuColor = s.cpu_percent > 70 ? 'fill-crimson' : (s.cpu_percent > 40 ? 'fill-amber' : 'fill-blue');
    const ramColor = s.ram_percent > 80 ? 'fill-crimson' : (s.ram_percent > 60 ? 'fill-amber' : 'fill-blue');
    const diskColor = s.disk_used_percent > 90 ? 'fill-crimson' : (s.disk_used_percent > 75 ? 'fill-amber' : 'fill-green');

    card.innerHTML = `
      <div class="card-top">
        <div class="station-name-box">
          <div class="st-title">${escapeHtml(s.station_name)}</div>
          <div class="st-user font-mono">${escapeHtml(s.username || 'user')} • ${escapeHtml(s.ip_address || '127.0.0.1')}</div>
        </div>
        <span class="st-status-badge ${badgeClass}">${badgeText}</span>
      </div>

      <div class="active-window-box">
        <span class="aw-label">АКТИВНОЕ ОКНО СЕЙЧАС:</span>
        <span class="aw-title ${s.game_detected ? 'game-warn' : ''}" title="${escapeHtml(s.active_window || '')}">
          ${s.game_detected ? '⚠️ ' : ''}${escapeHtml(s.active_window || 'Рабочий стол')}
        </span>
      </div>

      <div class="gauges-box font-mono">
        <div class="gauge-row">
          <span>CPU: ${s.cpu_percent}%</span>
          <div class="gauge-bar-wrap">
            <div class="gauge-bar-fill ${cpuColor}" style="width: ${Math.min(100, s.cpu_percent)}%;"></div>
          </div>
        </div>
        <div class="gauge-row">
          <span>RAM: ${s.ram_percent}%</span>
          <div class="gauge-bar-wrap">
            <div class="gauge-bar-fill ${ramColor}" style="width: ${Math.min(100, s.ram_percent)}%;"></div>
          </div>
        </div>
        <div class="gauge-row">
          <span style="${s.disk_alert ? 'color:#F59E0B; font-weight:700;' : ''}">ДИСК C: ${s.disk_free_gb} GB своб. (${s.disk_used_percent}%)</span>
          <div class="gauge-bar-wrap">
            <div class="gauge-bar-fill ${diskColor}" style="width: ${Math.min(100, s.disk_used_percent)}%;"></div>
          </div>
        </div>
      </div>

      <div class="card-actions">
        <button class="btn-card" onclick="sendStationAction('${s.station_id}', 'ROLLBACK')" title="Откатить ПК к эталону">🔄 Откат</button>
        <button class="btn-card" onclick="sendStationAction('${s.station_id}', '${s.is_locked ? 'UNLOCK' : 'LOCK'}')" title="${s.is_locked ? 'Разблокировать экран' : 'Заблокировать экран'}">
          ${s.is_locked ? '🔓 Разблок' : '🔒 Блок'}
        </button>
        <button class="btn-card" onclick="openScreenshotModal('${s.station_id}', '${escapeHtml(s.station_name)}')" title="Смотреть экран ученика">👁️ Экран</button>
        <button class="btn-card danger" onclick="sendStationAction('${s.station_id}', 'REBOOT')" title="Перезагрузить ПК ученика">⚡ Ребут</button>
      </div>
    `;

    stationsGrid.appendChild(card);
  });
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// Station specific actions
window.sendStationAction = async function(stationId, action) {
  if (action === 'ROLLBACK') {
    if (!confirm(`Откатить станцию ${stationId} к эталонному состоянию? Все несохраненные файлы ученика на Рабочем столе и в Загрузках будут удалены!`)) return;
  } else if (action === 'REBOOT') {
    if (!confirm(`Перезагрузить станцию ${stationId}?`)) return;
  }

  try {
    const res = await fetch(`/api/stations/${stationId}/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Команда [${action}] отправлена на ${stationId}`, 'success');
      setTimeout(fetchLogs, 1000);
    }
  } catch (err) {
    showToast(`Ошибка отправки команды: ${err.message}`, 'error');
  }
};

// Global Broadcast Actions
async function sendBroadcast(action, confirmMsg) {
  if (confirmMsg && !confirm(confirmMsg)) return;

  try {
    const res = await fetch('/api/broadcast', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Массовая операция [${action}] запущена на весь класс!`, 'success');
      setTimeout(fetchLogs, 1000);
    }
  } catch (err) {
    showToast(`Ошибка массовой операции: ${err.message}`, 'error');
  }
}

btnBroadcastRollback.addEventListener('click', () => {
  sendBroadcast('ROLLBACK', 'ВНИМАНИЕ! Вы запускаете полный сброс ВСЕХ компьютеров класса к эталонному снимку!\n\nВсе скачанные файлы учеников (Downloads, Desktop, Temp), игры, лишние ярлыки и процессы будут удалены. Продолжить?');
});

btnBroadcastSnapshot.addEventListener('click', () => {
  sendBroadcast('SNAPSHOT', 'Создать НОВЫЙ эталонный снимок на всех компьютерах?\nТекущее состояние каждого ПК станет образцом для будущих откатов.');
});

btnBroadcastLock.addEventListener('click', () => {
  sendBroadcast('LOCK', null);
});

btnBroadcastUnlock.addEventListener('click', () => {
  sendBroadcast('UNLOCK', null);
});

btnBroadcastPurge.addEventListener('click', () => {
  sendBroadcast('PURGE_DISK', 'Очистить временные папки и кэши на всех компьютерах для освобождения места на диске C:?');
});

btnBroadcastReboot.addEventListener('click', () => {
  sendBroadcast('REBOOT', 'Вы действительно хотите принудительно ПЕРЕЗАГРУЗИТЬ ВСЕ компьютеры класса?');
});

// Screenshot Modal
window.openScreenshotModal = async function(stationId, stationName) {
  activeViewingStationId = stationId;
  screenshotModalTitle.textContent = `ЭКРАН УЧЕНИКА: ${stationName} (${stationId})`;
  screenshotContainer.innerHTML = '<div class="loading-spinner">Запрос экрана у агента...</div>';
  screenshotModal.classList.add('open');

  await requestScreenshot();
};

async function requestScreenshot() {
  if (!activeViewingStationId) return;
  screenshotContainer.innerHTML = '<div class="loading-spinner" style="color:#38BDF8;">Получение кадра...</div>';
  try {
    const res = await fetch(`/api/stations/${activeViewingStationId}/screenshot`);
    const data = await res.json();
    if (data.screenshot) {
      screenshotContainer.innerHTML = `<img src="data:image/jpeg;base64,${data.screenshot}" alt="Снимок экрана">`;
    } else {
      screenshotContainer.innerHTML = '<div style="color:#F59E0B; text-align:center;">Команда отправлена агенту. Подождите пару секунд и нажмите «Обновить снимок».</div>';
    }
  } catch (err) {
    screenshotContainer.innerHTML = `<div style="color:#EF4444;">Ошибка: ${err.message}</div>`;
  }
}

btnRefreshScreenshot.addEventListener('click', requestScreenshot);
btnCloseScreenshotModal.addEventListener('click', () => screenshotModal.classList.remove('open'));
btnCloseScreenshotModalBtn.addEventListener('click', () => screenshotModal.classList.remove('open'));

// Assignment Deploy Modal
btnOpenAssignmentModal.addEventListener('click', () => {
  assignmentModal.classList.add('open');
});
btnCloseAssignmentModal.addEventListener('click', () => assignmentModal.classList.remove('open'));
btnCancelAssignment.addEventListener('click', () => assignmentModal.classList.remove('open'));

assignmentForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const title = document.getElementById('assignTitle').value.trim();
  const fileInput = document.getElementById('assignFile');
  if (!fileInput.files || fileInput.files.length === 0) {
    showToast('Выберите файл для раздачи!', 'warn');
    return;
  }

  const formData = new FormData();
  formData.append('title', title);
  formData.append('file', fileInput.files[0]);

  try {
    const submitBtn = document.getElementById('btnSubmitAssignment');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Отправка...';

    const res = await fetch('/api/assignments/deploy', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    if (data.success) {
      showToast(`Задание «${title}» успешно отправлено на все ПК!`, 'success');
      assignmentModal.classList.remove('open');
      assignmentForm.reset();
      fetchLogs();
    }
  } catch (err) {
    showToast(`Ошибка отправки задания: ${err.message}`, 'error');
  } finally {
    const submitBtn = document.getElementById('btnSubmitAssignment');
    submitBtn.disabled = false;
    submitBtn.textContent = '🚀 ОТПРАВИТЬ ВСЕМУ КЛАССУ';
  }
});

// Search filter listener
stationSearchInput.addEventListener('input', renderStations);
btnRefreshGrid.addEventListener('click', () => {
  fetchStations();
  fetchLogs();
  showToast('Данные обновлены', 'success');
});

// Periodic log polling
setInterval(fetchLogs, 5000);

// Init
connectWebSocket();
fetchStations();
fetchLogs();
