    const center = { lat: 55.7558, lon: 37.6173 }; 
    const NETWORK_TYPES = ["WiFi", "Bluetooth", "Cellular", "Ethernet"];
    const FOLDER_NAMES = ["MainFolder", "Backup", "Archive", "Temp"];
    const SYSTEM_FOLDERS = ["SysA", "SysB", "SysC", "SysDefault"];

    function rand(min, max){ return Math.random()*(max-min)+min; }
    function pick(arr){ return arr[Math.floor(Math.random()*arr.length)]; }
    function mac(){ return Array.from({length:6},()=>Math.floor(Math.random()*256).toString(16).padStart(2,'0')).join(":").toUpperCase(); }
    function dateTs(){ return Math.floor(Date.now() - rand(0, 30*24*3600*1000)); }
    function locationName(lat, lon){ return `Location near [${lat.toFixed(4)}, ${lon.toFixed(4)}]`; }

    function radialOffset(i, n){
      const radius = rand(50, 300); 
      const angle = (i / n) * Math.PI*2 + rand(-0.03, 0.03);
      const dLat = (radius * Math.cos(angle)) / 111320;
      const dLon = (radius * Math.sin(angle)) / (111320 * Math.cos(center.lat * Math.PI/180));
      return { lat: center.lat + dLat, lon: center.lon + dLon };
    }

    function generateDevices(n=500){
      const list = [];
      for(let i=0;i<n;i++){
        const {lat, lon} = radialOffset(i,n);
        const network = pick(NETWORK_TYPES);
        list.push({
          device_id: `DEV-${String(i+1).padStart(4,'0')}`,
          user_phone_mac: mac(),
          latitude: lat,
          longitude: lon,
          location: locationName(lat, lon),
          signal_strength: Math.round(rand(-100,-40)) + ' dBm',
          network_type: network,
          is_ignored: Math.random() < 0.15,
          is_alert: Math.random() < 0.1,
          user_api: `API_${Math.random().toString(36).slice(2,10).toUpperCase()}`,
          detected_at: dateTs(),
          folder_name: pick(FOLDER_NAMES),
          system_folder_name: pick(SYSTEM_FOLDERS)
        });
      }
      return list;
    }

    const state = {
      devices: generateDevices(500),
      filtered: [],
      page: 1,
      pageSize: 10,
      search: '',
      filters: { network:'any', deviceid:'', mac:'', alert:false, ignore:false },
      selectedId: null,
    };

    const map = L.map('map', { zoomControl: true }).setView([center.lat, center.lon], 13);
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
        const style = {
          radius: 8,
          color: d.is_alert ? '#ef4444' : '#4f46e5',
          fillColor: d.is_alert ? '#ef4444' : '#6366f1',
          weight: 2,
          fillOpacity: 0.2
        };
        const m = L.circleMarker([d.latitude, d.longitude], style)
          .bindPopup(`<b>${d.device_id}</b><br>${d.location}<br>${d.network_type}<br>Signal: ${d.signal_strength}`)
          .on('click', () => selectRow(d.device_id, true));
        m.addTo(markersLayer);
        markerById.set(d.device_id, m);
      });
    }

    function flyTo(id){
      const m = markerById.get(id);
      if(!m) return;
      map.flyTo(m.getLatLng(), 16, { duration: .8 });
      setTimeout(()=>m.openPopup(), 850);
    }

    const tbody = document.querySelector('#devicesTable tbody');
    const showing = document.getElementById('showing');
    const pagination = document.getElementById('pagination');

    function renderTable(){
      const start = (state.page-1)*state.pageSize;
      const end = Math.min(start + state.pageSize, state.filtered.length);
      const slice = state.filtered.slice(start, end);

      tbody.innerHTML = slice.map(d => `
        <tr data-id="${d.device_id}">
          <td>${d.device_id}</td>
          <td>${d.user_phone_mac}</td>
          <td>${d.latitude.toFixed(5)}</td>
          <td>${d.longitude.toFixed(5)}</td>
          <td>${d.location}</td>
          <td>${d.signal_strength}</td>
          <td>${d.network_type}</td>
          <td>${String(d.is_ignored)}</td>
          <td>${String(d.is_alert)}</td>
          <td>${d.user_api}</td>
          <td>${d.detected_at}</td>
          <td>${d.folder_name}</td>
          <td>${d.system_folder_name}</td>
        </tr>
      `).join('');


      tbody.querySelectorAll('tr').forEach(tr => {
        tr.addEventListener('click', () => selectRow(tr.dataset.id, true));
        tr.classList.toggle('active', tr.dataset.id === state.selectedId);
      });

      showing.textContent = `Отображено ${state.filtered.length ? start+1 : 0} до ${end} из ${state.filtered.length} записей`;

      const totalPages = Math.max(1, Math.ceil(state.filtered.length / state.pageSize));
      pagination.innerHTML = '';
      const prev = document.createElement('button');
      prev.textContent = 'Предыдущая'; prev.className = 'page'; prev.disabled = state.page===1;
      prev.onclick = ()=>{ state.page = Math.max(1, state.page-1); renderTable(); scrollToTableTop(); };
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
          b.onclick = ()=>{ state.page = p; renderTable(); scrollToTableTop(); };
        }
        pagination.appendChild(b);
      });

      const next = document.createElement('button');
      next.textContent = 'Следующая'; next.className = 'page'; next.disabled = state.page===totalPages;
      next.onclick = ()=>{ state.page = Math.min(totalPages, state.page+1); renderTable(); scrollToTableTop(); };
      pagination.appendChild(next);
    }

    function scrollToTableTop(){
      document.querySelector('.table-card .header').scrollIntoView({behavior:'smooth', block:'start'});
    }

    function selectRow(id, fly=false){
      state.selectedId = id;
      document.getElementById('selected-id').textContent = id || '—';
      tbody.querySelectorAll('tr').forEach(tr => tr.classList.toggle('active', tr.dataset.id===id));
      if(fly) flyTo(id);
    }

    function normalize(str){ return (str+"").toLowerCase(); }

    function applyFilters(){
      state.filters.network = document.getElementById('f-network').value;
      state.filters.deviceid = document.getElementById('f-deviceid').value.trim();
      state.filters.mac = document.getElementById('f-mac').value.trim();
      state.filters.alert = document.getElementById('f-alert').checked;
      state.filters.ignore = document.getElementById('f-ignore').checked;
      state.search = document.getElementById('topSearch').value.trim() || document.getElementById('tableSearch').value.trim();
      filterAndRender();
    }

    function filterAndRender(){
      const {network,deviceid,mac,alert,ignore} = state.filters;
      const q = normalize(state.search);
      state.filtered = state.devices.filter(d => {
        if(network !== 'any' && d.network_type !== network) return false;
        if(deviceid && !normalize(d.device_id).includes(normalize(deviceid))) return false;
        if(mac && !normalize(d.user_phone_mac).includes(normalize(mac))) return false;
        if(alert && !d.is_alert) return false;
        if(ignore && !d.is_ignored) return false;
        if(q){
          const blob = `${d.device_id} ${d.user_phone_mac} ${d.network_type} ${d.folder_name} ${d.system_folder_name}`.toLowerCase();
          if(!blob.includes(q)) return false;
        }
        return true;
      });
      state.page = 1;
      renderMarkers(state.filtered);
      renderTable();
      if(state.filtered.length){ selectRow(state.filtered[0].device_id); }
      else { selectRow(null); }
    }

    document.getElementById('pageSize').addEventListener('change', (e)=>{
      state.pageSize = parseInt(e.target.value,10);
      state.page = 1; renderTable();
    });
    document.getElementById('tableSearch').addEventListener('input', ()=>{
      state.search = document.getElementById('tableSearch').value.trim();
      filterAndRender();
    });

    (function init(){
      document.getElementById('pageSize').value = String(state.pageSize);
      filterAndRender();
    })();