import {getCheckboxesValues} from "./custom-elements.js";


function normalize(v){ return String(v ?? '').trim(); }
function timeParse(id){
  const timeElement = document.getElementById(id).value
  return timeElement ? new Date(timeElement).toISOString() : null
}

// Преобразует ISO в формат для Datatime-local
function toDatetimeLocalValue(date) {
  const d = new Date(date);
  const pad = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}` +
         `T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function parseCSV(value) {
  if (!value) return [];
  return value.split(",").map(v => v.trim()).filter(Boolean);
}

function parseBool(value) {
  return value === "true";
}

// Возвращает значения всех фильтров на странице
export function getFilters(){
  return {
    apiKeys: getCheckboxesValues("apiList"),
    devices: getCheckboxesValues("deviceList"),
    folders: getCheckboxesValues("folderList"),

    network: document.getElementById('f-network').value,
    mac: normalize(document.getElementById('f-mac').value),
    name: normalize(document.getElementById('f-name').value),

    timeStart: timeParse("time-start"),
    timeEnd: timeParse("time-end"),

    alert: document.getElementById('f-alert').checked,
    ignore: document.getElementById('f-ignore').checked
  }
}

// Устанавливает значение фильтров на странице
export function setFilters(filters) {
  if (!filters) return;
  document.getElementById("f-network").value = filters.network;
  document.getElementById("f-mac").value = filters.mac;
  document.getElementById("f-name").value = filters.name;

  document.getElementById("time-start").value = filters.timeStart ? toDatetimeLocalValue(filters.timeStart) : '';
  document.getElementById("time-end").value = filters.timeEnd ? toDatetimeLocalValue(filters.timeEnd) : '';

  document.getElementById("f-alert").checked = filters.alert;
  document.getElementById("f-ignore").checked = filters.ignore;

  document.getElementById("f-network").dispatchEvent(new Event("change", { bubbles: true }));
}

export async function getFiltersFromBack(apiKey) {
  try {
    const res = await fetch(`${API_FILTERING}last/`, {
      method: "GET",
      headers: {
        "Authorization": `Api-Key ${apiKey}`,
        "Accept": "application/json",
      },
    });

    if (res.status === 403) {
      console.warn("API key invalid or user not found");
      return null;
    }

    if (!res.ok) {
      console.error("Failed to load filters:", res.status);
      return null;
    }

    return await res.json();
  } catch (err) {
    console.error("Network error while loading filters", err);
    return null;
  }
}


export function translateFiltersFromBack(raw = {}) {
  return {
    apiKeys: parseCSV(raw.user_api),
    devices: parseCSV(raw.user_phone_mac),
    folders: parseCSV(raw.folder_name),

    network: raw.network_type || "any",
    mac: raw.device_id || '',
    name: raw.name || '',

    timeStart: raw.detected_at__gte || null,
    timeEnd: raw.detected_at__lte || null,

    alert: parseBool(raw.is_alert),
    ignore: parseBool(raw.is_ignored)
  }
}
