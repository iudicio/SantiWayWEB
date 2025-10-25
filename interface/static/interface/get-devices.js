
async function postUserInfo(body){
  try {
    const response = await fetch(API_USER_INFO, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        'X-CSRFToken': getCookie('csrftoken')
      },
      body: JSON.stringify(body)
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`Ошибка ${response.status}: ${text}`);
    }

    return await response.json();
  } catch (err) {
    console.error("Ошибка запроса postUserInfo:", err);
    throw err;
  }
}

// Возвращает apiKey и его имя
async function getApiKeys(){
    const apiKeysResponse = await fetch("/api/api-key/", {
      method: "GET",
    });
    const apiKeys = await apiKeysResponse.json();
    console.log("API Keys:", apiKeys);
    return apiKeys
}

async function getDevices(apiKeys){
  if (!Array.isArray(apiKeys)) apiKeys = [apiKeys];
  const devices = await postUserInfo({api_keys: apiKeys});
  console.log("Количество полученных устройств: ", devices.length);
  return devices;
}

async function getFolders(apiKeys, devices) {
  if (!Array.isArray(apiKeys)) apiKeys = apiKeys ? [apiKeys] : [];
  if (!Array.isArray(devices)) devices = devices ? [devices] : [];

  // Проверка на пустые массивы
  if (apiKeys.length === 0) {
    console.warn("getFolders: Запрос получения папок отменён — список API пустой");
    return [];
  }

  if (devices.length === 0) {
    console.warn("getFolders: Запрос получения отменён — список устройств пустой");
    return [];
  }

  try {
    return await postUserInfo({api_keys: apiKeys, devices});
  } catch (err) {
    console.error("getFolders: Ошибка при получении папок:", err);
    return [];
  }
}

function getCookie(name){
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}