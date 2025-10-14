const API_BASE = (window.APP_CONFIG && window.APP_CONFIG.API_BASE) || '/api';
const API_KEY = (window.APP_CONFIG && window.APP_CONFIG.API_KEY) || '';
const API_DEVICES_URL = `${API_BASE}/devices/`;
const API_POLYGONS_URL = `${API_BASE}/polygons/`;

class NotificationSystem {
  constructor() {
    this.container = document.getElementById('notificationContainer');
  }

  show(message, type = 'info', title = '', duration = 5000) {
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    
    const icons = {
      success: '✓',
      error: '✕',
      warning: '⚠',
      info: 'ℹ'
    };

    notification.innerHTML = `
      <div class="notification-icon">${icons[type] || icons.info}</div>
      <div class="notification-content">
        ${title ? `<div class="notification-title">${title}</div>` : ''}
        <div class="notification-message">${message}</div>
      </div>
      <button class="notification-close" onclick="this.parentElement.remove()">×</button>
    `;

    this.container.appendChild(notification);
    
    setTimeout(() => notification.classList.add('show'), 100);
    
    if (duration > 0) {
      setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
      }, duration);
    }
  }

  success(message, title = 'Успешно') {
    this.show(message, 'success', title);
  }

  error(message, title = 'Ошибка') {
    this.show(message, 'error', title);
  }

  warning(message, title = 'Предупреждение') {
    this.show(message, 'warning', title);
  }

  info(message, title = 'Информация') {
    this.show(message, 'info', title);
  }
}

const notifications = new NotificationSystem();

const state = {
  rows: [],
  total: 0,
  page: 1,
  pageSize: 10,
  search: '',
  filters: { network: 'any', deviceid: '', mac: '', alert: false, ignore: false },
  selectedId: null,
  apiKey: (window.APP_CONFIG && window.APP_CONFIG.API_KEY) || '',
  colorForPolygon: {} // Используется как хранилище цветов, чтобы при каждом reload() не слать запросы на сервер
};

// Цвета полигонов в зависимости от статуса
const POLYGON_COLORS = {
  DEFAULT: "#ef4444",   // Неактивный/неизвестный
  RUNNING: "#0b60de",   // Мониторинг идет
  COMPLETED: "#22c55e", // Завершен
  STOPPED: "#9ca3af"    // Остановлен
};

if (!state.apiKey){alert('Для корректной работы сайта создайте API-ключ в профиле и перезагрузите эту страницу');}

function normalize(v){ return String(v ?? '').trim(); }
function toBool(v){ return v ? 'true' : 'false'; }
function formatCoord(n){ return (Number(n) || 0).toFixed(5); }
function formatDetectedAt(v){
  if(!v) return '—';
  let d;
  if (typeof v === 'number') {
    d = new Date(v > 1e12 ? v : v * 1000);
  } else {
    d = new Date(v);
  }
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toLocaleString();
}

const center = { lat: 55.7558, lon: 37.6173 };

const map = L.map('map', {
  zoomControl: true,
  attributionControl: true,
}).setView([center.lat, center.lon], 13);

L.Control.Attribution.prototype.options.prefix = '';

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

const markersLayer = L.layerGroup().addTo(map);
const polygonsLayer = L.featureGroup().addTo(map);

// Рисование полигонов (Leaflet.draw)
let drawControl;
let drawnItems = polygonsLayer;

function ensureDrawTools(){
  
  if (drawControl) {
    console.log('drawControl already exists, returning');
    return;
  }
  
  drawControl = new L.Control.Draw({
    edit: {
      featureGroup: polygonsLayer,
      poly: { allowIntersection: false },
      edit: true,
      remove: true
    },
    draw: {
      polygon: {
        allowIntersection: false,
        showArea: true,
        shapeOptions: { color: '#ef4444', weight: 2, fillOpacity: 0.15 }
      },
      rectangle: {
        showArea: true,
        shapeOptions: { color: '#ef4444', weight: 2, fillOpacity: 0.15 }
      },
      circle: false,
      circlemarker: false,
      marker: false,
      polyline: false
    }
  });
  map.addControl(drawControl);

  // События Leaflet.draw

  // Используем события на уровне карты
  map.on('draw:created', async (e) => {
    const layer = e.layer;

    let ring = [];
    
    const latlngs = (layer.getLatLngs?.()[0]) || [];

    if (latlngs.length >= 3) {
      ring = latlngs.map(ll => [Number(ll.lng), Number(ll.lat)]);
      if (ring[0][0] !== ring[ring.length-1][0] || ring[0][1] !== ring[ring.length-1][1]) {
        ring.push([ring[0][0], ring[0][1]]);
      }
      
    } else {
      
      return;
    }

    const payload = {
      name: `Area ${Date.now()}`,
      description: '',
      geometry: { type: 'Polygon', coordinates: [ ring ] },
      is_active: true
    };

    try{
      const res = await fetch(API_POLYGONS_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
          'Authorization': `Api-Key ${state.apiKey}`
        },
        body: JSON.stringify(payload)
      });
      if(!res.ok) throw new Error(`API ${res.status}`);
      // Получение id и добавление его в объект colorForPolygon
      const data = await res.json();
      state.colorForPolygon[data.id] = POLYGON_COLORS.DEFAULT;
      await reload();
    } catch(err){ console.error('Polygon create failed', err); }
  });

  // Используем события на уровне карты для редактирования
  map.on('draw:edited', async (e) => {
    const layers = e.layers;
    const updates = [];
    layers.eachLayer(l => {
      let ring = [];
      
      const latlngs = (l.getLatLngs?.()[0]) || [];
      
      if (latlngs.length >= 3) {
        ring = latlngs.map(ll => [Number(ll.lng), Number(ll.lat)]);
        if (ring[0][0] !== ring[ring.length-1][0] || ring[0][1] !== ring[ring.length-1][1]) {
          ring.push([ring[0][0], ring[0][1]]);
        }
        
      } else {
        
        return;
      }
      
      const pid = l.options && l.options._pid;
      if(pid){
        updates.push({ id: pid, geometry: { type: 'Polygon', coordinates: [ ring ] } });
        
      }
    });

    for(const u of updates){
      try{
        const res = await fetch(`${API_POLYGONS_URL}${u.id}/`, {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': `Api-Key ${state.apiKey}`
          },
          body: JSON.stringify({ geometry: u.geometry })
        });
        if(!res.ok) throw new Error(`API ${res.status}`);
      } catch(err){ console.error('Polygon update failed', err); }
    }
    await reload();
  });

  map.on('draw:deleted', async (e) => {
    
    const layers = e.layers;
    const ids = [];
    layers.eachLayer(l => {
      const pid = l.options && l.options._pid;
      if(pid) ids.push(pid);
    });
    for(const id of ids){
      try{
        const res = await fetch(`${API_POLYGONS_URL}${id}/`, {
          method: 'DELETE',
          headers: {
            'Accept': 'application/json',
            'Authorization': `Api-Key ${state.apiKey}`
          }
        });
        if(!res.ok) throw new Error(`API ${res.status}`);
      } catch(err){ console.error('Polygon delete failed', err); }
    }
    await reload();
  });
}

const markerById = new Map();

function renderMarkers(rows){
  markersLayer.clearLayers();
  markerById.clear();
  rows.forEach(d => {
    const lat = Number(d.latitude);
    const lon = Number(d.longitude);
    if (Number.isFinite(lat) && Number.isFinite(lon)) {
      const style = {
        radius: 8,
        color: d.is_alert ? '#ef4444' : '#4f46e5',
        fillColor: d.is_alert ? '#ef4444' : '#6366f1',
        weight: 2,
        fillOpacity: 0.2
      };
      const m = L.circleMarker([lat, lon], style)
        .bindPopup(`
          <b>${d.device_id ?? '—'}</b><br/>
          ${d.location ?? '—'}<br/>
          ${d.network_type ?? '—'}<br/>
          Signal: ${d.signal_strength ?? '—'}
        `.trim())
        .on('click', () => selectRow(d.device_id, true));
      m.addTo(markersLayer);
      if (d.device_id) markerById.set(d.device_id, m);
    }
  });
}

function flyTo(id){
  const m = markerById.get(id);
  if(!m) return;
  map.flyTo(m.getLatLng(), 16, { duration: .8 });
  setTimeout(()=>m.openPopup(), 850);
}

// Таблица/пагинация 
const tbody = document.querySelector('#devicesTable tbody');
const showing = document.getElementById('showing');

function renderTable(){
  tbody.innerHTML = state.rows.map(d => `
    <tr data-id="${d.device_id ?? ''}">
      <td>${d.device_id ?? '—'}</td>
      <td>${d.user_phone_mac ?? '—'}</td>
      <td>${formatCoord(d.latitude)}</td>
      <td>${formatCoord(d.longitude)}</td>
      <td>${d.location ?? '—'}</td>
      <td>${d.signal_strength ?? '—'}</td>
      <td>${d.network_type ?? '—'}</td>
      <td>${String(!!d.is_ignored)}</td>
      <td>${String(!!d.is_alert)}</td>
      <td>${d.user_api ?? '—'}</td>
      <td>${formatDetectedAt(d.detected_at)}</td>
      <td>${d.folder_name ?? '—'}</td>
      <td>${d.system_folder_name ?? '—'}</td>
    </tr>
  `).join('');

  tbody.querySelectorAll('tr').forEach(tr => {
    tr.addEventListener('click', () => selectRow(tr.dataset.id, true));
    tr.classList.toggle('active', tr.dataset.id === state.selectedId);
  });

  const start = state.total ? (state.page - 1) * state.pageSize + 1 : 0;
  const end   = Math.min(state.page * state.pageSize, state.total);
  showing.textContent = `Отображено ${start} до ${end} из ${state.total} записей`;

  const totalPages = Math.max(1, Math.ceil(state.total / state.pageSize));

  const prev = document.getElementById('prevPage');
  prev.textContent = 'Предыдущая'; prev.disabled = state.page===1;
  prev.onclick = ()=>{ state.page = Math.max(1, state.page-1); reload(); };

  const pages = [];
  const startPage = Math.max(1, state.page-3);
  const endPage = Math.min(totalPages, state.page+3);
  for(let p=startPage;p<=endPage;p++) pages.push(p);
  if(startPage>1){ pages.unshift(1); if(startPage>2) pages.splice(1,0,'…'); }
  if(endPage<totalPages){ if(endPage<totalPages-1) pages.push('…'); pages.push(totalPages); }

  pages.forEach(p => {
    const b = document.createElement('button');
    b.className = 'page'; b.textContent = p;
    if(p === '…'){ b.disabled = true; }
    else {
      if(p === state.page) b.classList.add('active');
      b.onclick = ()=>{ state.page = p; reload(); };
    }
  });

  const next = document.getElementById('nextPage');
  next.textContent = 'Следующая'; next.disabled = state.page===totalPages;
  next.onclick = ()=>{ state.page = Math.min(totalPages, state.page+1); reload(); };
}

function selectRow(id, fly=false){
  state.selectedId = id || null;
  document.getElementById('selected-id').textContent = id || '—';
  tbody.querySelectorAll('tr').forEach(tr => tr.classList.toggle('active', tr.dataset.id===id));
  if(fly && id) flyTo(id);
}

// Загрузка с API
function buildQuery(){
  const qs = new URLSearchParams();
  qs.set('page', state.page);
  qs.set('page_size', state.pageSize);

  const f = state.filters;
  if (f.network && f.network !== 'any') qs.set('network_type', f.network);
  if (f.deviceid) qs.set('device_id', f.deviceid);
  if (f.mac) qs.set('user_phone_mac', f.mac);
  if (f.alert) qs.set('is_alert', 'true');
  if (f.ignore) qs.set('is_ignored', 'true');

  if (state.search) qs.set('q', state.search);

  return qs.toString();
}

async function fetchDevices() {
  const url = `${API_DEVICES_URL}?${buildQuery()}`;
  const res = await fetch(url, { 
    headers: { 
      'Accept': 'application/json',
      'Authorization': `Api-Key ${state.apiKey}`
    }
  });
  if(!res.ok) throw new Error(`API ${res.status}`);

  const data = await res.json();

  if (Array.isArray(data)) {
    return { rows: data, total: data.length };
  }
  if ('results' in data && Array.isArray(data.results)) {
    return { rows: data.results, total: Number(data.count) || data.results.length };
  }
  if (Array.isArray(data.items)) {
    return { rows: data.items, total: Number(data.total) || data.items.length };
  }
  return { rows: Array.isArray(data) ? data : [], total: Array.isArray(data) ? data.length : 0 };
}

async function reload(){
  try{
    const { rows, total } = await fetchDevices();
    const polygons = await fetchPolygons();
    // Шлем на сервер запросы только при загрузке страницы в первый раз
    if (Object.keys(state.colorForPolygon).length === 0){ state.colorForPolygon= await getAllPolygonsColor(polygons);}

    state.rows = rows;
    state.total = total;
    renderMarkers(rows);
    renderPolygons(polygons, state.colorForPolygon);
    renderTable();
    if(rows.length){ selectRow(rows[0].device_id); }
    else { selectRow(null); }
  } catch (e){
    console.error(e);
    tbody.innerHTML = `<tr><td colspan="13">Ошибка загрузки данных: ${e.message}</td></tr>`;
    showing.textContent = '';
    markersLayer.clearLayers();
  }
}

// Фильтры/события 
document.getElementById('btnApplyFilters').addEventListener('click', () => {
  state.filters.network  = document.getElementById('f-network').value;
  state.filters.deviceid = normalize(document.getElementById('f-deviceid').value);
  state.filters.mac      = normalize(document.getElementById('f-mac').value);
  state.filters.alert    = document.getElementById('f-alert').checked;
  state.filters.ignore   = document.getElementById('f-ignore').checked;
  state.page = 1;
  reload();
});

document.getElementById('tableSearch').addEventListener('input', ()=>{
  state.search = normalize(document.getElementById('tableSearch').value);
  state.page = 1;
  reload();
});

document.getElementById('pageSize').addEventListener('change', (e)=>{
  state.pageSize = parseInt(e.target.value,10) || 10;
  state.page = 1;
  reload();
});

async function fetchPolygons(){
  const res = await fetch(API_POLYGONS_URL, {
    headers: {
      'Accept': 'application/json',
      'Authorization': `Api-Key ${state.apiKey}`
    }
  });
  if(!res.ok) throw new Error(`API ${res.status}`);
  return await res.json();
}

function renderPolygons(rows, colors){
  polygonsLayer.clearLayers();
  if(!Array.isArray(rows)) return;
  rows.forEach(p => {
    try{
      console.log('Rendering polygon:', p);
      console.log('Polygon ID:', p.id, 'Type:', typeof p.id);
      if(!p.geometry || p.geometry.type !== 'Polygon') return;
      const ring = p.geometry.coordinates?.[0] || [];
      if(ring.length < 4) return;
      const latlngs = ring.map(([lon,lat]) => [lat,lon]);
          const poly = L.polygon(latlngs, {
            color: colors[p.id],
            weight: 2,
            fillColor: colors[p.id],
            fillOpacity: 0.15,
            _pid: p.id
          }).bindPopup(`
            <div class="popup-title">${p.name || 'Polygon'}</div>
            <div class="popup-info">
              <strong>Площадь:</strong> ${p.area ? p.area.toFixed(2) + ' км²' : 'N/A'}<br/>
              <strong>Создан:</strong> ${new Date(p.created_at).toLocaleString('ru-RU')}<br/>
              <strong>Статус:</strong> ${p.is_active ? 'Активен' : 'Неактивен'}
            </div>
            <div class="action-buttons" data-pid="${String(p.id)}">
              <button class="action-btn search js-action-search">🔍 Поиск устройств</button>
              <button class="action-btn monitor js-action-start">📊 Запустить мониторинг</button>
              <button class="action-btn stop js-action-stop">⏹️ Остановить мониторинг</button>
              <button class="action-btn status js-action-status">📈 Статус мониторинга</button>
              <button class="action-btn delete js-delete-polygon">❌ Удалить полигон</button>
            </div>
          `);
      poly.on('popupopen', (ev) => {
        try{
          const container = ev.popup.getElement();
          const actions = container && container.querySelector('.action-buttons');
          if(!actions) return;
          const pid = String(actions.getAttribute('data-pid'));
          
          const on = (sel, fn) => { const el = actions.querySelector(sel); if(el) el.onclick = () => fn(pid); };
          on('.js-action-search', (id) => window.searchDevicesInPolygon && window.searchDevicesInPolygon(String(id)));
          on('.js-action-start',  (id) => window.startMonitoring && window.startMonitoring(String(id)));
          on('.js-action-stop',   (id) => window.stopMonitoring && window.stopMonitoring(String(id)));
          on('.js-action-status', (id) => window.checkMonitoringStatus && window.checkMonitoringStatus(String(id)));
          on('.js-delete-polygon', (id) => window.deletePolygon && window.deletePolygon(String(id)));
        } catch(e){ console.warn('popupopen binding error', e); }
      });
      poly.addTo(polygonsLayer);
    } catch(e){ console.warn('polygon render error', e); }
  });
}

window.searchDevicesInPolygon = async function searchDevicesInPolygon(polygonId) {
  try {
    const response = await fetch(`${API_POLYGONS_URL}${polygonId}/search/`, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Authorization': `Api-Key ${state.apiKey}`,
        'Content-Type': 'application/json'
      }
    });
    
    if (!response.ok) {
      throw new Error(`API ${response.status}`);
    }
    
    const result = await response.json();
    
    if (result.devices && result.devices.length > 0) {
      markersLayer.clearLayers();
      
      result.devices.forEach(device => {
        if (device.location && device.location.lat && device.location.lon) {
          const marker = L.marker([device.location.lat, device.location.lon], {
            icon: L.divIcon({
              className: 'search-result-marker',
              html: '🔍',
              iconSize: [20, 20]
            })
          }).bindPopup(`
            <div class="popup-title">Найденное устройство</div>
            <div class="popup-info">
              <strong>Device ID:</strong> ${device.device_id || 'N/A'}<br/>
              <strong>MAC:</strong> ${device.mac || 'N/A'}<br/>
              <strong>Время:</strong> ${device.timestamp || 'N/A'}
            </div>
          `);
          marker.addTo(markersLayer);
        }
      });
      
      notifications.success(`Найдено устройств: ${result.devices_found}`, 'Поиск завершен');
    } else {
      notifications.warning('Устройства в полигоне не найдены', 'Поиск завершен');
    }
    
  } catch (error) {
    console.error('Ошибка поиска устройств:', error);
    notifications.error(`Ошибка поиска: ${error.message}`);
  }
}

window.startMonitoring = async function startMonitoring(polygonId) {
  try {
    const response = await fetch(`${API_POLYGONS_URL}${polygonId}/start_monitoring/`, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Authorization': `Api-Key ${state.apiKey}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        monitoring_interval: 300 // 5 минут
      })
    });

    if (!response.ok) {
      const errorData = await response.json();
      throw new Error(errorData.error || `API ${response.status}`);
    }

    changePolygonColor(polygonId, POLYGON_COLORS.RUNNING);
    const result = await response.json();
    
    notifications.success(`Мониторинг запущен!<br/>Интервал: ${result.monitoring_interval} сек<br/>Task ID: ${result.task_id}`, 'Мониторинг активен');
    
  } catch (error) {
    console.error('Ошибка запуска мониторинга:', error);
    notifications.error(`Ошибка запуска мониторинга: ${error.message}`);
  }
}

window.stopMonitoring = async function stopMonitoring(polygonId) {
  try {
    const response = await fetch(`${API_POLYGONS_URL}${polygonId}/stop_monitoring/`, {
      method: 'POST',
      headers: {
        'Accept': 'application/json',
        'Authorization': `Api-Key ${state.apiKey}`,
        'Content-Type': 'application/json'
      }
    });
    
    if (!response.ok) {
      throw new Error(`API ${response.status}`);
    }

    changePolygonColor(polygonId, POLYGON_COLORS.STOPPED);
    const result = await response.json();
    
    notifications.success(`Мониторинг остановлен для полигона: ${result.polygon_name}`);
    
  } catch (error) {
    console.error('Ошибка остановки мониторинга:', error);
    notifications.error(`Ошибка остановки мониторинга: ${error.message}`);
  }
}

window.checkMonitoringStatus = async function checkMonitoringStatus(polygonId) {
  try {
    const response = await fetch(`${API_POLYGONS_URL}${polygonId}/monitoring_status/`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Authorization': `Api-Key ${state.apiKey}`
      }
    });
    
    if (!response.ok) {
      throw new Error(`API ${response.status}`);
    }
    
    const result = await response.json();
    
    let statusText = '';
    switch(result.monitoring_status) {
      case 'not_started':
        statusText = 'Мониторинг не запущен';
        break;
      case 'running':
        statusText = 'Мониторинг активен';
        break;
      case 'stopped':
        statusText = 'Мониторинг остановлен';
        break;
      case 'completed':
        statusText = 'Мониторинг завершен';
        break;
      default:
        statusText = 'Неизвестный статус';
    }

    let actionsInfo = '';
    if (result.actions && result.actions.length > 0) {
      const lastAction = result.actions[0];
      actionsInfo = `
        <div class="card">
          <strong>Последнее действие:</strong><br/>
          Статус: <span class="status-badge small ${lastAction.status === 'running' ? 'running' : 'stopped'}">
            <span class="status-dot"></span>
            ${lastAction.status === 'running' ? 'Активен' : 'Остановлен'}
          </span><br/>
          Создано: ${new Date(lastAction.created_at).toLocaleString('ru-RU')}
          ${lastAction.parameters && lastAction.parameters.last_mac_count !== undefined ? 
            `<br/>Найдено MAC адресов: <strong>${lastAction.parameters.last_mac_count}</strong>` : ''}
        </div>
      `;
    }

    const modal = document.createElement('div');
    modal.className = 'modal-overlay show';
    modal.innerHTML = `
       <div class="modal">
          <div class="modal-header">
            <h3 class="modal-title">📊 Статус мониторинга</h3>
            <button class="modal-close">&#10005;</button>
          </div>
          <div class="modal-body">
            <div class="modal-status-block">
              <div class="status-indicator ${result.monitoring_status}">${statusText}</div>
            </div>
            <div class="modal-polygon-block">
              <div class="modal-polygon-name">
                Полигон: ${result.polygon_name || 'N/A'}
              </div>
            </div>
            ${actionsInfo}
          </div>
          <div class="modal-footer">
            <button class="btn-primary modal-btn-close">Закрыть</button>
          </div>
        </div>
    `;
    document.body.appendChild(modal);

    const closeBtn = modal.querySelector('.modal-close');
    const actionBtn = modal.querySelector('.btn-primary');

    const closeModal = () => modal.remove();

    closeBtn.addEventListener('click', closeModal);
    actionBtn.addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        modal.remove();
      }
    });
    
  } catch (error) {
    console.error('Ошибка проверки статуса мониторинга:', error);
    notifications.error(`Ошибка проверки статуса: ${error.message}`);
  }
}

window.deletePolygon = async function deletePolygon(polygonId) {
  try {
    const response = await fetch(`${API_POLYGONS_URL}${polygonId}/`, {
      method: 'DELETE',
      headers: {
        'Accept': 'application/json',
        'Authorization': `Api-Key ${state.apiKey}`
      }
    });
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.error || errorData.detail || `HTTP ${response.status}`);
    }
    
    delete state.colorForPolygon[polygonId];
    
    await reload();
    
    notifications.success(`Полигон успешно удалён`, 'Удаление завершено');
    
  } catch (error) {
    console.error('Ошибка удаления полигона:', error);
    notifications.error(`Ошибка удаления полигона: ${error.message}`);
  }
}

// Получение цветов для всех полигонов
async function getAllPolygonsColor(polygons) {
  const colorForPolygon = {}; // локальный словарь

  for (const p of polygons) {
    try {
      const res = await fetch(`${API_POLYGONS_URL}${p.id}/monitoring_status/`, {
        headers: {
          'Accept': 'application/json',
          'Authorization': `Api-Key ${state.apiKey}`
        }
      });

      if (res.ok) {
        const data = await res.json();
        console.log(`Status: ${data.monitoring_status}`)
        switch (data.monitoring_status) {
          case 'running': colorForPolygon[p.id] = POLYGON_COLORS.RUNNING; break;
          case 'stopped': colorForPolygon[p.id] = POLYGON_COLORS.STOPPED; break;
          case 'completed': colorForPolygon[p.id] = POLYGON_COLORS.COMPLETED; break;
          default: colorForPolygon[p.id] = POLYGON_COLORS.DEFAULT;
        }
      } else {
        colorForPolygon[p.id] = POLYGON_COLORS.DEFAULT;
      }
    } catch {
      colorForPolygon[p.id] = POLYGON_COLORS.DEFAULT;
    }
  }
  return colorForPolygon;
}

// Меняет цвет полигона на карте и в colorForPolygon по его ID
function changePolygonColor(id, newColor= POLYGON_COLORS.DEFAULT){
  state.colorForPolygon[id] = newColor;
  let poly = polygonsLayer.getLayers().find(p => p.options._pid == id);
    if (poly) {
      poly.setStyle({
        color: newColor,
        fillColor: newColor,
        fillOpacity: 0.15
      });
    }
}

// Объявляем переменную для менеджера уведомлений
let notificationManager;

// Класс для управления уведомлениями
class NotificationManager {
  constructor() {
    this.notifications = [];
    this.unreadCount = 0;
    this.isPolling = false;
    this.pollInterval = null;
    
    this.initElements();
    this.bindEvents();
    this.startPolling();
  }

  initElements() {
    this.notificationsBtn = document.getElementById('notificationsBtn');
    this.notificationsBadge = document.getElementById('notificationsBadge');
    this.notificationsPanel = document.getElementById('notificationsPanel');
    this.notificationsOverlay = document.getElementById('notificationsOverlay');
    this.notificationsCloseBtn = document.getElementById('notificationsCloseBtn');
    this.notificationsBody = document.getElementById('notificationsBody');
    this.notificationsEmpty = document.getElementById('notificationsEmpty');
  }

  bindEvents() {
    if (this.notificationsBtn) {
      this.notificationsBtn.addEventListener('click', () => this.togglePanel());
    }
    if (this.notificationsCloseBtn) {
      this.notificationsCloseBtn.addEventListener('click', () => this.closePanel());
    }
    if (this.notificationsOverlay) {
      this.notificationsOverlay.addEventListener('click', () => this.closePanel());
    }
  }

  togglePanel() {
    if (this.notificationsPanel.classList.contains('open')) {
      this.closePanel();
    } else {
      this.openPanel();
    }
  }

  openPanel() {
    this.notificationsPanel.classList.add('open');
    this.notificationsOverlay.classList.add('show');
    this.loadNotifications();
  }

  closePanel() {
    this.notificationsPanel.classList.remove('open');
    this.notificationsOverlay.classList.remove('show');
  }

  async loadNotifications() {
    try {
      const response = await fetch(`${API_BASE}/notifications/`, {
        headers: {
          'Authorization': `Api-Key ${API_KEY}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      this.notifications = data.results || data;
      this.renderNotifications();
    } catch (error) {
      console.error('Ошибка загрузки уведомлений:', error);
      notifications.error('Не удалось загрузить уведомления');
    }
  }

  async checkUnreadCount() {
    try {
      const response = await fetch(`${API_BASE}/notifications/unread_count/`, {
        headers: {
          'Authorization': `Api-Key ${API_KEY}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      this.updateUnreadCount(data.unread_count);
    } catch (error) {
      console.error('Ошибка проверки непрочитанных уведомлений:', error);
    }
  }

  updateUnreadCount(count) {
    this.unreadCount = count;
    
    if (count > 0) {
      this.notificationsBadge.textContent = count > 99 ? '99+' : count;
      this.notificationsBadge.style.display = 'flex';
      this.notificationsBtn.classList.add('has-new');
    } else {
      this.notificationsBadge.style.display = 'none';
      this.notificationsBtn.classList.remove('has-new');
    }
  }

  renderNotifications() {
    if (!this.notifications || this.notifications.length === 0) {
      this.notificationsEmpty.style.display = 'block';
      return;
    }

    this.notificationsEmpty.style.display = 'none';
    
    const notificationsHtml = this.notifications.map(notification => {
      const isUnread = ['pending', 'sent', 'delivered'].includes(notification.status);
      const timeAgo = this.formatTimeAgo(notification.created_at);
      
      return `
        <div class="notification-item ${isUnread ? 'unread' : ''}" 
             data-id="${notification.id}" 
             onclick="notificationManager.markAsRead('${notification.id}')">
          <div class="notification-item-header">
            <h4 class="notification-item-title">${notification.title}</h4>
            <span class="notification-item-time">${timeAgo}</span>
          </div>
          <p class="notification-item-message">${notification.message}</p>
          <div class="notification-item-meta">
            <span class="notification-badge severity-${notification.anomaly_details?.severity || 'medium'}">
              ${this.getSeverityText(notification.anomaly_details?.severity)}
            </span>
            <span class="notification-badge type">
              ${this.getAnomalyTypeText(notification.anomaly_details?.anomaly_type)}
            </span>
          </div>
        </div>
      `;
    }).join('');

    this.notificationsBody.innerHTML = notificationsHtml;
  }

  async markAsRead(notificationId) {
    try {
      const response = await fetch(`${API_BASE}/notifications/${notificationId}/mark_as_read/`, {
        method: 'POST',
        headers: {
          'Authorization': `Api-Key ${API_KEY}`,
          'Content-Type': 'application/json'
        }
      });

      if (response.ok) {
        const notification = this.notifications.find(n => n.id === notificationId);
        if (notification) {
          notification.status = 'read';
        }
        
        this.renderNotifications();
        this.checkUnreadCount();
      }
    } catch (error) {
      console.error('Ошибка отметки уведомления как прочитанного:', error);
    }
  }

  getSeverityText(severity) {
    const severityMap = {
      'low': 'Низкая',
      'medium': 'Средняя', 
      'high': 'Высокая',
      'critical': 'Критическая'
    };
    return severityMap[severity] || 'Средняя';
  }

  getAnomalyTypeText(anomalyType) {
    const typeMap = {
      'new_device': 'Новое устройство',
      'suspicious_activity': 'Подозрительная активность',
      'signal_anomaly': 'Аномалия сигнала',
      'location_anomaly': 'Аномалия местоположения',
      'frequency_anomaly': 'Аномалия частоты',
      'unknown_vendor': 'Неизвестный производитель'
    };
    return typeMap[anomalyType] || 'Аномалия';
  }

  formatTimeAgo(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffMins < 1) return 'Только что';
    if (diffMins < 60) return `${diffMins} мин назад`;
    if (diffHours < 24) return `${diffHours} ч назад`;
    if (diffDays < 7) return `${diffDays} д назад`;
    
    return date.toLocaleDateString('ru-RU');
  }

  startPolling() {
    if (this.isPolling) return;
    
    this.isPolling = true;
    this.checkUnreadCount();
    
    this.pollInterval = setInterval(() => {
      this.checkUnreadCount();
    }, 30000); // каждые 30 секунд
  }

  stopPolling() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
    this.isPolling = false;
  }

  showNewNotification(notification) {
    const severity = notification.anomaly_details?.severity || 'medium';
    const type = severity === 'critical' ? 'error' : 
                 severity === 'high' ? 'warning' : 'info';
    
    notifications.show(
      notification.message,
      type,
      notification.title,
      8000
    );
    
    this.checkUnreadCount();
  }
}

// Инициализация
;(function init(){
  console.log('Initializing app...');
  document.getElementById('pageSize').value = String(state.pageSize);
  console.log('Calling ensureDrawTools...');
  ensureDrawTools();
  console.log('Calling reload...');
  reload();
  console.log('App initialized');
  
  // Инициализируем менеджер уведомлений
  if (API_KEY && API_KEY.trim() !== '') {
    console.log('Initializing notification manager...');
    notificationManager = new NotificationManager();
  } else {
    console.log('API key not available, skipping notification manager initialization');
  }
})();

