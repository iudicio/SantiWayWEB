const API_BASE = (window.APP_CONFIG && window.APP_CONFIG.API_BASE) || '/api';
const API_DEVICES_URL = `${API_BASE}/devices/`; 

const state = {
  rows: [],
  total: 0,
  page: 1,
  pageSize: 10,
  search: '',
  filters: { network: 'any', deviceid: '', mac: '', alert: false, ignore: false },
  selectedId: null,
};

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
const pagination = document.getElementById('pagination');

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
  pagination.innerHTML = '';

  const prev = document.createElement('button');
  prev.textContent = 'Предыдущая'; prev.className = 'page'; prev.disabled = state.page===1;
  prev.onclick = ()=>{ state.page = Math.max(1, state.page-1); reload(); };
  pagination.appendChild(prev);

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
    pagination.appendChild(b);
  });

  const next = document.createElement('button');
  next.textContent = 'Следующая'; next.className = 'page'; next.disabled = state.page===totalPages;
  next.onclick = ()=>{ state.page = Math.min(totalPages, state.page+1); reload(); };
  pagination.appendChild(next);
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

async function fetchDevices(){
  const url = `${API_DEVICES_URL}?${buildQuery()}`;
  const res = await fetch(url, { headers: { 'Accept': 'application/json' }});
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
    state.rows = rows;
    state.total = total;
    renderMarkers(rows);
    renderTable();
    if(rows.length){ selectRow(rows[0].device_id); }
    else { selectRow(null); }
  } catch (e){
    console.error(e);
    tbody.innerHTML = `<tr><td colspan="13">Ошибка загрузки данных: ${e.message}</td></tr>`;
    showing.textContent = '';
    pagination.innerHTML = '';
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

document.getElementById('btnTopSearch').addEventListener('click', () => {
  state.search = normalize(document.getElementById('topSearch').value) || normalize(document.getElementById('tableSearch').value);
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

// Инициализация
(function init(){
  document.getElementById('pageSize').value = String(state.pageSize);
  reload();
})();