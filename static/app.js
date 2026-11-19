// IT-Class Guardian // Teacher Dashboard Client Logic v2.0
// ZERO-MOCK PRODUCTION ARCHITECTURE

let stationsData = [];
let activeViewingStationId = null;
let ws = null;
let isTestAgentRunning = false;

// DOM Elements
const stationsGrid = document.getElementById('stationsGrid');
const metricOnlineCount = document.getElementById('metricOnlineCount');
const metricDiskAlerts = document.getElementById('metricDiskAlerts');
const metricGameAlerts = document.getElementById('metricGameAlerts');
const stationsGridHeader = document.getElementById('stationsGridHeader');
const stationSearchInput = document.getElementById('stationSearchInput');
const btnRefreshGrid = document.getElementById('btnRefreshGrid');
const logsTableBody = document.getElementById('logsTableBody');
const teacherIpBadge = document.getElementById('teacherIpBadge');

// Ribbon buttons
const btnBroadcastRollback = document.getElementById('btnBroadcastRollback');
const btnBroadcastSnapshot = document.getElementById('btnBroadcastSnapshot');
const btnBroadcastLock = document.getElementById('btnBroadcastLock');
const btnBroadcastUnlock = document.getElementById('btnBroadcastUnlock');
const btnBroadcastPurge = document.getElementById('btnBroadcastPurge');
const btnBroadcastReboot = document.getElementById('btnBroadcastReboot');
const btnOpenAssignmentModal = document.getElementById('btnOpenAssignmentModal');
const btnStartTeacherBroadcast = document.getElementById('btnStartTeacherBroadcast');
const btnStopTeacherBroadcast = document.getElementById('btnStopTeacherBroadcast');
const btnToggleViewMode = document.getElementById('btnToggleViewMode');
const metricBroadcastStatus = document.getElementById('metricBroadcastStatus');

// Connect & Scan Buttons
const btnOpenConnectModal = document.getElementById('btnOpenConnectModal');
const btnOpenScanModal = document.getElementById('btnOpenScanModal');
const btnToggleTestAgent = document.getElementById('btnToggleTestAgent');

// Connect Modal
const connectModal = document.getElementById('connectModal');
const connectForm = document.getElementById('connectForm');
const btnCloseConnectModal = document.getElementById('btnCloseConnectModal');
const btnCancelConnect = document.getElementById('btnCancelConnect');
const connectStatusOutput = document.getElementById('connectStatusOutput');

// Scan Modal
const scanModal = document.getElementById('scanModal');
const btnCloseScanModal = document.getElementById('btnCloseScanModal');
const btnExecuteScan = document.getElementById('btnExecuteScan');
const scanProgressArea = document.getElementById('scanProgressArea');
const scanResultsList = document.getElementById('scanResultsList');

// Screenshot Modal
const screenshotModal = document.getElementById('screenshotModal');
const screenshotContainer = document.getElementById('screenshotContainer');
const screenshotModalTitle = document.getElementById('screenshotModalTitle');
const btnCloseScreenshotModal = document.getElementById('btnCloseScreenshotModal');
const btnCloseScreenshotModalBtn = document.getElementById('btnCloseScreenshotModalBtn');
const btnRefreshScreenshot = document.getElementById('btnRefreshScreenshot');

// Assignment Modal
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

function formatTime(ts) {
  if (!ts) return '-';
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

// Network Info
async function fetchNetworkInfo() {
  try {
    const res = await fetch('/api/network/info');
    const data = await res.json();
    if (teacherIpBadge && data.teacher_ip) {
      teacherIpBadge.textContent = `${data.teacher_ip}:${data.port}`;
    }
  } catch (err) {
    console.error('Failed to fetch network info:', err);
  }
}

// WebSocket Connection
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
        stationsData = msg.stations || [];
        renderStations();
        updateTopMetrics();
        updateBroadcastState(msg.broadcast_active);
        if (msg.teacher_ip && teacherIpBadge) {
          teacherIpBadge.textContent = `${msg.teacher_ip}:8023`;
        }
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

// Fetch Stations
async function fetchStations() {
  try {
    const res = await fetch('/api/stations');
    const data = await res.json();
    stationsData = data.stations || [];
    renderStations();
    updateTopMetrics();
    updateBroadcastState(data.broadcast_active);
    if (data.teacher_ip && teacherIpBadge) {
      teacherIpBadge.textContent = `${data.teacher_ip}:8023`;
    }
  } catch (err) {
    console.error('Failed to fetch stations:', err);
  }
}

// Fetch Logs
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
    logsTableBody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:#60606A; padding:15px;">Журнал пуст (действий ещё не совершалось)</td></tr>';
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
  stationsGridHeader.textContent = `Всего мест: ${total} • Активно онлайн: ${online}`;
}

// Render Classroom Stations Grid (ZERO MOCK POLICY)
function renderStations() {
  const query = stationSearchInput.value.toLowerCase().trim();
  stationsGrid.innerHTML = '';

  // If no stations exist in DB -> Show Empty State Guide
  if (stationsData.length === 0) {
    stationsGrid.innerHTML = `
      <div class="empty-stations-box">
        <div class="empty-icon">🛡️</div>
        <div class="empty-title">РАБОЧИЕ СТАНЦИИ УЧЕНИКОВ НЕ ПОДКЛЮЧЕНЫ</div>
        <div class="empty-desc">
          Все заглушки отключены. Система готова к подключению реальных компьютеров кабинета.<br>
          Выберите удобный способ подключения рабочих станций:
        </div>
        <div class="connect-options-grid">
          <div class="conn-card">
            <div class="conn-num">1</div>
            <div class="conn-card-title">Автоматически (LAN Beacon)</div>
            <div class="conn-card-desc">
              Запустите <b>«Агент_Ученика.exe»</b> на ПК учеников. Агент работает полностью <b>в фоне без окон</b> и сам мгновенно связывается с учителем по локальной сети.
            </div>
          </div>
          <div class="conn-card">
            <div class="conn-num">2</div>
            <div class="conn-card-title">Подключить ПК по IP</div>
            <div class="conn-card-desc">
              Введите IP-адрес ученика в сети класса, и сервер учителя сам отправит команду привязки на ПК ученика.
            </div>
            <button class="btn btn-small btn-primary" onclick="openConnectModal()">➕ Подключить по IP</button>
          </div>
          <div class="conn-card">
            <div class="conn-num">3</div>
            <div class="conn-card-title">Сканирование сети класса</div>
            <div class="conn-card-desc">
              Сервер опросит подсеть кабинета и автоматически привяжет все включенные компьютеры учащихся.
            </div>
            <button class="btn btn-small btn-accent" onclick="openScanModal()">🔍 Сканировать LAN</button>
          </div>
        </div>
        <div class="test-local-bar">
          <span>Хотите проверить систему прямо сейчас на этом компьютере?</span>
          <button class="btn btn-small btn-outline" id="btnStartLocalQuick" onclick="toggleTestAgent()">
            ▶ Запустить скрытого тестового агента (127.0.0.1)
          </button>
        </div>
      </div>
    `;
    return;
  }

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
    stationsGrid.innerHTML = '<div style="grid-column: 1/-1; padding: 30px; text-align: center; color: #8E8E98;">Компьютеры по запросу не найдены</div>';
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
        <div style="display:flex; align-items:center; gap:6px;">
          <span class="st-status-badge ${badgeClass}">${badgeText}</span>
          <button class="btn-delete-station" onclick="deleteStation('${s.station_id}', '${escapeHtml(s.station_name)}')" title="Удалить это место из списка">✕</button>
        </div>
      </div>

      <!-- Live Screen Miniature (Veyon Matrix) -->
      <div class="station-thumbnail-box" onclick="openScreenshotModal('${s.station_id}', '${escapeHtml(s.station_name)}')" title="Кликните для просмотра полноразмерного экрана">
        ${s.latest_thumbnail ? `<img src="data:image/jpeg;base64,${s.latest_thumbnail}" class="thumbnail-img" alt="Экран">` : `<div style="color:#60606A; font-size:11px;">(Ожидание кадра)</div>`}
        <span class="thumbnail-overlay-live">● LIVE ЭКРАН</span>
        ${s.game_detected ? `<span class="thumbnail-overlay-warn">⚠️ ИГРА</span>` : ''}
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
        <button class="btn-card" onclick="sendStationAction('${s.station_id}', '${s.is_locked ? 'UNLOCK' : 'LOCK'}')" title="${s.is_locked ? 'Разблокировать' : 'Заблокировать'}">
          ${s.is_locked ? '🔓 Разблок' : '🔒 Блок'}
        </button>
        <button class="btn-card" onclick="openScreenshotModal('${s.station_id}', '${escapeHtml(s.station_name)}')" title="Смотреть экран ученика">👁️ Экран</button>
        <button class="btn-card danger" onclick="sendStationAction('${s.station_id}', 'REBOOT')" title="Перезагрузить ПК">⚡ Ребут</button>
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
    if (!confirm(`Откатить станцию ${stationId} к эталону? Все несохраненные файлы ученика в Downloads и Desktop будут удалены!`)) return;
  } else if (action === 'REBOOT') {
    if (!confirm(`Перезагрузить компьютер ученика ${stationId}?`)) return;
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

// Delete / Disconnect Station
window.deleteStation = async function(stationId, stationName) {
  if (!confirm(`Удалить рабочее место «${stationName}» (${stationId}) из списка класса?`)) return;
  try {
    const res = await fetch(`/api/stations/${stationId}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.success) {
      showToast(`Рабочее место ${stationName} удалено`, 'warn');
      fetchStations();
      fetchLogs();
    }
  } catch (err) {
    showToast(`Ошибка удаления: ${err.message}`, 'error');
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
      showToast(`Операция [${action}] запущена на весь класс!`, 'success');
      setTimeout(fetchLogs, 1000);
    }
  } catch (err) {
    showToast(`Ошибка: ${err.message}`, 'error');
  }
}

btnBroadcastRollback.addEventListener('click', () => {
  sendBroadcast('ROLLBACK', 'Сбросить ВСЕ компьютеры класса к чистому эталону?\n\nВсе новые файлы учеников в Загрузках и на Рабочем столе, игры и лишние процессы будут удалены.');
});

btnBroadcastSnapshot.addEventListener('click', () => {
  sendBroadcast('SNAPSHOT', 'Зафиксировать текущее чистое состояние компьютеров как эталонный снимок?');
});

btnBroadcastLock.addEventListener('click', () => sendBroadcast('LOCK', null));
btnBroadcastUnlock.addEventListener('click', () => sendBroadcast('UNLOCK', null));
btnBroadcastPurge.addEventListener('click', () => sendBroadcast('PURGE_DISK', 'Очистить временные файлы и кэш на всех ПК?'));
btnBroadcastReboot.addEventListener('click', () => sendBroadcast('REBOOT', 'Принудительно перезагрузить ВСЕ компьютеры класса?'));

// Teacher Screen Broadcast
function updateBroadcastState(isActive) {
  if (isActive) {
    if (btnStartTeacherBroadcast) btnStartTeacherBroadcast.style.display = 'none';
    if (btnStopTeacherBroadcast) btnStopTeacherBroadcast.style.display = 'inline-flex';
    if (metricBroadcastStatus) {
      metricBroadcastStatus.textContent = '🔴 АКТИВНА [ВЕСЬ КЛАСС]';
      metricBroadcastStatus.className = 'm-val val-crimson';
    }
  } else {
    if (btnStartTeacherBroadcast) btnStartTeacherBroadcast.style.display = 'inline-flex';
    if (btnStopTeacherBroadcast) btnStopTeacherBroadcast.style.display = 'none';
    if (metricBroadcastStatus) {
      metricBroadcastStatus.textContent = '⏹ ВЫКЛ';
      metricBroadcastStatus.className = 'm-val';
    }
  }
}

let screenCaptureStream = null;
let screenCaptureInterval = null;

async function startTeacherBroadcast() {
  try {
    const res = await fetch('/api/broadcast/start_screen', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      updateBroadcastState(true);
      showToast('Трансляция экрана учителя запущена на весь класс!', 'success');

      if (navigator.mediaDevices && navigator.mediaDevices.getDisplayMedia) {
        try {
          screenCaptureStream = await navigator.mediaDevices.getDisplayMedia({ video: { cursor: 'always' }, audio: false });
          const video = document.createElement('video');
          video.srcObject = screenCaptureStream;
          video.play();

          const canvas = document.createElement('canvas');
          const ctx = canvas.getContext('2d');

          screenCaptureInterval = setInterval(() => {
            if (!screenCaptureStream || !screenCaptureStream.active) {
              stopTeacherBroadcast();
              return;
            }
            if (video.videoWidth > 0 && video.videoHeight > 0) {
              canvas.width = Math.min(1280, video.videoWidth);
              canvas.height = Math.round((canvas.width / video.videoWidth) * video.videoHeight);
              ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
              const dataUrl = canvas.toDataURL('image/jpeg', 0.6);
              const b64 = dataUrl.split(',')[1];
              fetch('/api/broadcast/push_frame', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ frame_b64: b64 })
              }).catch(() => {});
            }
          }, 250);

          screenCaptureStream.getVideoTracks()[0].onended = () => {
            stopTeacherBroadcast();
          };
        } catch (streamErr) {
          console.log('Browser capture skipped, using server-side loop:', streamErr);
        }
      }
    }
  } catch (err) {
    showToast(`Ошибка: ${err.message}`, 'error');
  }
}

async function stopTeacherBroadcast() {
  if (screenCaptureInterval) {
    clearInterval(screenCaptureInterval);
    screenCaptureInterval = null;
  }
  if (screenCaptureStream) {
    screenCaptureStream.getTracks().forEach(t => t.stop());
    screenCaptureStream = null;
  }
  try {
    await fetch('/api/broadcast/stop_screen', { method: 'POST' });
    updateBroadcastState(false);
    showToast('Трансляция экрана остановлена', 'warn');
  } catch (err) {
    showToast(`Ошибка: ${err.message}`, 'error');
  }
}

if (btnStartTeacherBroadcast) btnStartTeacherBroadcast.addEventListener('click', startTeacherBroadcast);
if (btnStopTeacherBroadcast) btnStopTeacherBroadcast.addEventListener('click', stopTeacherBroadcast);

if (btnToggleViewMode) {
  btnToggleViewMode.addEventListener('click', () => {
    stationsGrid.classList.toggle('veyon-matrix');
    const isVeyon = stationsGrid.classList.contains('veyon-matrix');
    btnToggleViewMode.textContent = isVeyon ? '🔲 СТАНДАРТНЫЙ ВИД' : '📺 РЕЖИМ VEYON (ЭКРАНЫ)';
    showToast(isVeyon ? 'Включена монитор-стена Veyon' : 'Включен стандартный режим', 'success');
  });
}

// Connect Student PC Modal Handlers
window.openConnectModal = function() {
  connectModal.classList.add('open');
  connectStatusOutput.style.display = 'none';
  document.getElementById('connectIp').focus();
};
if (btnOpenConnectModal) btnOpenConnectModal.addEventListener('click', openConnectModal);
if (btnCloseConnectModal) btnCloseConnectModal.addEventListener('click', () => connectModal.classList.remove('open'));
if (btnCancelConnect) btnCancelConnect.addEventListener('click', () => connectModal.classList.remove('open'));

connectForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const ip = document.getElementById('connectIp').value.trim();
  const port = parseInt(document.getElementById('connectPort').value, 10) || 8024;
  const name = document.getElementById('connectName').value.trim();

  const submitBtn = document.getElementById('btnSubmitConnect');
  submitBtn.disabled = true;
  submitBtn.textContent = 'Подключение...';
  connectStatusOutput.style.display = 'block';
  connectStatusOutput.style.color = '#38BDF8';
  connectStatusOutput.textContent = `Отправка запроса привязки на http://${ip}:${port} ...`;

  try {
    const res = await fetch('/api/stations/connect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ip, port, station_name: name || null })
    });
    const data = await res.json();
    if (data.success) {
      connectStatusOutput.style.color = '#34D399';
      connectStatusOutput.textContent = `Успешно! Рабочее место «${data.station_name}» подключено к кабинету.`;
      showToast(`ПК ${data.station_name} успешно подключен!`, 'success');
      setTimeout(() => {
        connectModal.classList.remove('open');
        fetchStations();
        fetchLogs();
      }, 1200);
    } else {
      connectStatusOutput.style.color = '#F87171';
      connectStatusOutput.textContent = `Ошибка: ${data.error}`;
    }
  } catch (err) {
    connectStatusOutput.style.color = '#F87171';
    connectStatusOutput.textContent = `Сетевая ошибка: ${err.message}`;
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = '🚀 ПОДКЛЮЧИТЬ К ПАНЕЛИ';
  }
});

// Scan Classroom LAN Modal Handlers
window.openScanModal = function() {
  scanModal.classList.add('open');
  scanProgressArea.style.display = 'none';
};
if (btnOpenScanModal) btnOpenScanModal.addEventListener('click', openScanModal);
if (btnCloseScanModal) btnCloseScanModal.addEventListener('click', () => scanModal.classList.remove('open'));

if (btnExecuteScan) {
  btnExecuteScan.addEventListener('click', async () => {
    btnExecuteScan.disabled = true;
    btnExecuteScan.textContent = '⏳ Идет сканирование подсети...';
    scanProgressArea.style.display = 'block';
    scanResultsList.innerHTML = '<div style="color:#A1A1AA; padding:8px;">Опрос адресов локальной сети (порт 8024)...</div>';

    try {
      const res = await fetch('/api/network/scan', { method: 'POST' });
      const data = await res.json();
      if (data.found_count > 0) {
        scanResultsList.innerHTML = '';
        data.found.forEach(st => {
          const item = document.createElement('div');
          item.className = 'scan-item';
          item.innerHTML = `
            <div>
              <b style="color:#34D399;">● НАЙДЕН:</b> ${escapeHtml(st.station_name || st.station_id)}
              <span style="color:#9CA3AF;">(${escapeHtml(st.ip)})</span>
            </div>
            <span style="color:#38BDF8; font-weight:700;">ПРИВЯЗАН</span>
          `;
          scanResultsList.appendChild(item);
        });
        showToast(`Найдено и подключено ПК: ${data.found_count}`, 'success');
        fetchStations();
        fetchLogs();
      } else {
        scanResultsList.innerHTML = `
          <div style="color:#F59E0B; padding:8px;">
            В подсети опрошено ${data.scanned_ips} адресов, активных агентов не обнаружено.<br>
            Убедитесь, что на ПК учеников запущен <b>«Агент_Ученика.exe»</b> (он слушает порт 8024).
          </div>
        `;
      }
    } catch (err) {
      scanResultsList.innerHTML = `<div style="color:#EF4444; padding:8px;">Ошибка сканирования: ${err.message}</div>`;
    } finally {
      btnExecuteScan.disabled = false;
      btnExecuteScan.textContent = '🔍 НАЧАТЬ СКАНИРОВАНИЕ ПОДСЕТИ';
    }
  });
}

// Local Test Agent Toggle (Background / Silent)
window.toggleTestAgent = async function() {
  try {
    if (!isTestAgentRunning) {
      const res = await fetch('/api/test_agent/start', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        isTestAgentRunning = true;
        showToast('Скрытый агент запущен в фоне (без окна)', 'success');
        if (btnToggleTestAgent) {
          btnToggleTestAgent.textContent = '⏹ ОСТАНОВИТЬ ТЕСТОВЫЙ АГЕНТ';
          btnToggleTestAgent.className = 'btn btn-danger btn-small';
        }
        setTimeout(fetchStations, 1500);
      }
    } else {
      const res = await fetch('/api/test_agent/stop', { method: 'POST' });
      const data = await res.json();
      if (data.success) {
        isTestAgentRunning = false;
        showToast('Тестовый агент остановлен', 'warn');
        if (btnToggleTestAgent) {
          btnToggleTestAgent.textContent = '▶ ТЕСТОВЫЙ АГЕНТ (127.0.0.1)';
          btnToggleTestAgent.className = 'btn btn-secondary';
        }
        setTimeout(fetchStations, 1000);
      }
    }
  } catch (err) {
    showToast(`Ошибка: ${err.message}`, 'error');
  }
};
if (btnToggleTestAgent) btnToggleTestAgent.addEventListener('click', toggleTestAgent);

// Screenshot Modal
window.openScreenshotModal = async function(stationId, stationName) {
  activeViewingStationId = stationId;
  screenshotModalTitle.textContent = `ЭКРАН УЧЕНИКА: ${stationName} (${stationId})`;
  screenshotContainer.innerHTML = '<div class="loading-spinner">Запрос экрана...</div>';
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

if (btnRefreshScreenshot) btnRefreshScreenshot.addEventListener('click', requestScreenshot);
if (btnCloseScreenshotModal) btnCloseScreenshotModal.addEventListener('click', () => screenshotModal.classList.remove('open'));
if (btnCloseScreenshotModalBtn) btnCloseScreenshotModalBtn.addEventListener('click', () => screenshotModal.classList.remove('open'));

// Assignment Deploy Modal
if (btnOpenAssignmentModal) {
  btnOpenAssignmentModal.addEventListener('click', () => assignmentModal.classList.add('open'));
}
if (btnCloseAssignmentModal) btnCloseAssignmentModal.addEventListener('click', () => assignmentModal.classList.remove('open'));
if (btnCancelAssignment) btnCancelAssignment.addEventListener('click', () => assignmentModal.classList.remove('open'));

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

  const submitBtn = document.getElementById('btnSubmitAssignment');
  submitBtn.disabled = true;
  submitBtn.textContent = 'Отправка...';

  try {
    const res = await fetch('/api/assignments/deploy', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.success) {
      showToast(`Задание «${title}» успешно отправлено на все ПК!`, 'success');
      assignmentModal.classList.remove('open');
      assignmentForm.reset();
      fetchLogs();
    }
  } catch (err) {
    showToast(`Ошибка отправки: ${err.message}`, 'error');
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = '🚀 ОТПРАВИТЬ ВСЕМУ КЛАССУ';
  }
});

// Search & Refresh
stationSearchInput.addEventListener('input', renderStations);
btnRefreshGrid.addEventListener('click', () => {
  fetchStations();
  fetchLogs();
  fetchNetworkInfo();
  showToast('Данные обновлены', 'success');
});

// Periodic log polling
setInterval(fetchLogs, 5000);

// Init
fetchNetworkInfo();
connectWebSocket();
fetchStations();
fetchLogs();
