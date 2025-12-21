/* ============================
 Генератор тестовых устройств

 Режимы:
 1) UNIQUE      — каждое устройство с уникальным MAC
 2) DUPLICATES  — несколько записей с одним MAC
                 (проверка "последнего появления")

 Использование:
 fakeGen(apiKey, {
   mode: FAKE_GEN_MODE.UNIQUE,
   count: 50
 });

 fakeGen(apiKey, {
   mode: FAKE_GEN_MODE.DUPLICATES,
   uniqueMacs: 10,
   recordsPerMac: [2, 3, 4, 6]
 });
 ============================ */

export const FAKE_GEN_MODE = {
  UNIQUE: "unique",
  DUPLICATES: "duplicates",
};

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

function generateDeviceBase(mac, userApi, detectedAt) {
  const folder = randomChoice(folders);

  return {
    device_id: mac,
    latitude: randomFloat(moscowBounds.south, moscowBounds.north),
    longitude: randomFloat(moscowBounds.west, moscowBounds.east),
    signal_strength: Math.floor(Math.random() * 56 - 95),
    network_type: randomChoice(networks),
    is_ignored: randomBool(0.2),
    is_alert: randomBool(0.3),
    user_api: userApi,
    user_phone_mac: mac,
    detected_at: detectedAt,
    folder_name: folder.name,
    system_folder_name: folder.sys
  };
}

function generateUniqueDevices(count, userApi) {
  return Array.from({ length: count }, () => {
    const mac = randomMac();
    const detectedAt = new Date(
      Date.now() - Math.random() * 7 * 24 * 3600 * 1000
    ).toISOString();

    return generateDeviceBase(mac, userApi, detectedAt);
  });
}

function generateDuplicateDevices(
  uniqueMacsCount,
  recordsPerMac,
  userApi
) {
  const devices = [];

  for (let i = 0; i < uniqueMacsCount; i++) {
    const mac = randomMac();
    const recordsCount =
      typeof recordsPerMac === "number"
        ? recordsPerMac
        : randomChoice(recordsPerMac);

    for (let j = 0; j < recordsCount; j++) {
      const detectedAt = new Date(
        Date.now() - (recordsCount - j) * 15 * 60 * 1000
      ).toISOString();

      devices.push(
        generateDeviceBase(mac, userApi, detectedAt)
      );
    }
  }

  return devices;
}

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

export async function fakeGen(
  apiKey,
  {
    mode = FAKE_GEN_MODE.UNIQUE,
    count = 25,
    uniqueMacs = 5,
    recordsPerMac = 4,
  } = {}
) {
  let devices = [];

  if (mode === FAKE_GEN_MODE.DUPLICATES) {
    devices = generateDuplicateDevices(
      uniqueMacs,
      recordsPerMac,
      apiKey
    );
  } else {
    devices = generateUniqueDevices(count, apiKey);
  }

  console.log(
    `[FakeGen] mode=${mode}, records=${devices.length}`
  );
  console.table(
    devices.map(d => ({
      mac: d.device_id,
      detected_at: d.detected_at,
    }))
  );

  await sendDevices(devices, apiKey);
}
