/* ============================
 Генератор случайных устройств

 Для генерации необходимо необходимо:
    1. Подннять Vendor, ESWriter, RabbitMQ
    2. В dashboard.html вставить сразу после определения <script>... const API_... = ...;</script>
      <script type="module" src="{% static 'interface/jsTestGenerators/generateFakeDataTest.js' %}"></script>
    3. В app.js в самом начале добавить: 
      import { fakeGen } from "./jsTestGenerators/generateFakeDataTest.js";
    4. В функцию init() в app.js добавить в самый конец (после вызова initList()) 
    (25 - число генерируемых устройств), устройства будут генерироваться в пределах МСК:
      if (state.apiKey){
        fakeGen(state.apiKey,  25);
      } else alert("Для генерации нужен api ключ, создай в профиле");
    5. Пересобрать корневой докер
    6. После первой загрузки сайта, если все хорошо, то в консоли будет: 
      Status: 202 generateFakeDataTest.js:100
      {"status":"queued"} generateFakeDataTest.js:101
    7. После этого нужно убрать вызов функции fakeGen из app.js дабы не генерировать при каждой загрузке страницы новые утсройства
    8. Пересобрать докер, чтобы увидеть созаддыне устройства и не генерировать новые.
    9. Обновлять страницу желательно через Ctrl+F5, чтобы исключить вероятность подгрузки данных из кэша
 ============================
*/ 

function randomMac() {
  return Array.from({ length: 6 }, () =>
    Math.floor(Math.random() * 256).toString(16).padStart(2, "0").toUpperCase()
  ).join(":");
}

function randomFloat(min, max, decimals = 6) {
  return parseFloat((Math.random() * (max - min) + min).toFixed(decimals));
}

function randomChoice(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

function randomBool(probTrue = 0.3) {
  return Math.random() < probTrue;
}

// Списки для "папок"
const folders = [
  { name: "HQ/Main Lobby", sys: "hq_main_lobby" },
  { name: "Warehouse/Back Yard", sys: "warehouse_back_yard" },
  { name: "Office/2nd Floor", sys: "office_2nd_floor" },
  { name: "Store/Entrance", sys: "store_entrance" },
];

// Сети
const networks = ["WiFi", "LTE", "Bluetooth"];

// Пример координат
const baseCoords = [
  { lat: 55.755826, lon: 37.617299 }, // Москва
  { lat: 59.931058, lon: 30.360909 }, // СПБ
  { lat: 55.008353, lon: 82.935733 }, // Новосибирск
  { lat: 56.838926, lon: 60.605702 }, // Екатеринбург
  { lat: 55.796127, lon: 49.106414 }, // Казань
];
const moscowBounds = {
  north: 55.907,   // Северная граница (примерно МКАД)
  south: 55.579,   // Южная граница
  west: 37.368,    // Западная граница
  east: 37.855     // Восточная граница
};

function generateDevice(userApi) {
  const folder = randomChoice(folders);
  const mac = randomMac();
  const detectedAt = new Date(Date.now() - Math.random() * 7 * 24 * 3600 * 1000).toISOString(); // последние 7 дней

  return {
    device_id: mac,
    latitude: randomFloat(moscowBounds.south, moscowBounds.north),
    longitude: randomFloat(moscowBounds.west, moscowBounds.east),
    signal_strength: Math.floor(Math.random() * 56 - 95), // -95..-40 dBm
    network_type: randomChoice(networks),
    is_ignored: randomBool(0.2),
    is_alert: randomBool(0.3),
    user_api: userApi,          // <- теперь корректно передаётся
    user_phone_mac: mac,
    detected_at: detectedAt,
    folder_name: folder.name,
    system_folder_name: folder.sys
  };
}

// Генерация списка устройств
function generateDevices(count = 5, userApi) {
  return Array.from({ length: count }, () => generateDevice(userApi));
}

// ============================
// Отправка на сервер
// ============================

async function sendDevices(devices, apiKey) {
  const url = "/api/devices/";

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Api-Key ${apiKey}`
      },
      body: JSON.stringify(devices)
    });

    const data = await res.text(); // можно json(), если сервер возвращает JSON
    console.log(`Status: ${res.status}`);
    console.log(data);
  } catch (err) {
    console.error("Ошибка при отправке:", err);
  }
}

// ============================
// Обёртка для генерации и отправки
// ============================

export async function fakeGen(apiKey, devicesCount = 3) {
  const devices = generateDevices(devicesCount, apiKey);
  console.log(devices);

  await sendDevices(devices, apiKey);
}
