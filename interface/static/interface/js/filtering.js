import {getCheckboxesValues} from "./custom-elements.js";

const STORAGE_KEY = "dashboard.filters";

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

export function getFiltersFromBack() {
//   Тут будет fetch
}

// Сохранение полей фильтров в localStorage
export function saveFiltersToLocalStorage(filters) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(filters));
}

// Получение полей фильтров из LocalStorage
export function getFiltersFromLocalStorage() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    console.error('Не удалось прочитать фильтры из localStorage', e);
    return null;
  }
}


