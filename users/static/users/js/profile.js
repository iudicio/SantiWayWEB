document.addEventListener("DOMContentLoaded", () => {
  const STATUSES = { order: "order", create: "create", ready: "ready", failed: "failed" };
  const androidBtn = document.querySelectorAll(".apk-btn");
  const openModalBtn = document.getElementById('openModalBtn');
  const timeToCheck = 20000; // Запрос к серверу каждые 20 секунд
  let firstAlert = true;


  // Вешаем фукнцияю создания апи ключа на кнопку
  if (openModalBtn) {
    openModalBtn.addEventListener('click', function () {
      // Используем prompt для ввода названия ключа
      const keyName = prompt('Enter a name for your new API key:', 'My API Key');

      // Если пользователь не отменил ввод и ввел не пустую строку
      if (keyName !== null && keyName.trim() !== '') {
        // Здесь можно отправить запрос на сервер для создания ключа
        createApiKey(keyName.trim());
      } else if (keyName !== null) {
        // Если введена пустая строка
        alert('Please enter a valid name for the API key.');
      }
    });
  }

  // Для уже созданных элементов проходимся и вешаем обработчики
  androidBtn.forEach(button => {
    prepareButton(button);
    button.addEventListener("click", () => { changeAPKButtonState(button) });
    clearButtonLoading(button);
  })

  document.querySelectorAll(".mono").forEach(el => {
    el.addEventListener("click", () => { copyApiKey(el.textContent); copyApiKeyAnimation(el) });
  });

  // Функция для создания API ключа
  function createApiKey(name) {
    console.log('Creating API key with name:', name);

    // Отправляем POST запрос на сервер
    fetch('/api/api-key/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken')
      },
      body: JSON.stringify({ name: name })
    })
      .then(response => {
        if (!response.ok) {
          return response.json().then(errorData => {
            throw new Error(errorData.error || 'Network response was not ok');
          });
        }
        return response.json();
      })
      .then(data => {
        // Показываем пользователю созданный API ключ
        alert(`API key created successfully!\n\nDevice: ${data.device_name}\nAPI Key: ${data.api_key}\n\nPlease save this key - it won't be shown again!`);
        console.log("Data: ", data);
        addNewDeviceRow(data.device_name, data.api_key, data.device_id);
      })
      .catch(error => {
        console.error('Error:', error);
        alert('Error: ' + error.message);
      });
  }

  function addNewDeviceRow(deviceName, apiKey, deviceId) {
    const tbody = document.querySelector('#devicesTable tbody');

    // Убираем "Нет созданных API ключей"
    if (tbody.querySelector('td[colspan]')) {
      tbody.innerHTML = '';
    }

    // Создаем элементы вручную
    const tr = document.createElement('tr');

    // Название устройства
    const tdName = document.createElement('td');
    tdName.textContent = deviceName;

    // API ключ
    const tdKey = document.createElement('td');
    const pKey = document.createElement('p');
    pKey.className = 'mono text-center';
    pKey.textContent = apiKey;
    tdKey.appendChild(pKey);

    // Дата создания
    const tdDate = document.createElement('td');
    tdDate.className = 'text-center';
    tdDate.textContent = new Date().toISOString().split('T')[0];

    // Кнопка APK
    const tdApk = document.createElement('td');
    tdApk.className = 'text-center';
    const apkBtn = document.createElement('button');
    apkBtn.className = 'apk-btn btn-primary';
    apkBtn.textContent = 'Собрать APK';
    apkBtn.dataset.deviceId = deviceId;
    apkBtn.setAttribute("data-status", STATUSES.order);
    apkBtn.setAttribute("api-key", apiKey);
    tdApk.appendChild(apkBtn);
    apkBtn.addEventListener("click", () => { changeAPKButtonState(apkBtn) });

    // Кнопка удаления
    const tdDelete = document.createElement('td');
    tdDelete.className = 'delete-column';
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'remove-btn delete-btn';
    deleteBtn.innerHTML = '&#10005;';
    deleteBtn.onclick = function () { deleteDevice(deviceId, deviceName); };
    tdDelete.appendChild(deleteBtn);

    // Собираем строку
    tr.appendChild(tdName);
    tr.appendChild(tdKey);
    tr.appendChild(tdDate);
    tr.appendChild(tdApk);
    tr.appendChild(tdDelete);

    // Добавляем в таблицу
    tbody.appendChild(tr);
    //    NOTE: временное решение, тк при создании api-ключа id, по которому он потом удаляется не возвращается api
    location.reload();
  }
// Анимация для копирования APIключа
  function copyApiKeyAnimation(element) {
    const original = element.textContent;
    element.textContent = 'Скопировано!';
    const key = element.textContent.trim();
    navigator.clipboard.writeText(original).then(() => {
      element.classList.add("copied");
      setTimeout(() => element.classList.remove("copied"), 1500);
      setTimeout(() => element.textContent = original, 1500);
    });
  }

  // Функция для копирования API ключа
  function copyApiKey(key) {
    navigator.clipboard.writeText(key)
      .then(() => {
        alert('API key copied to clipboard!');
      })
      .catch(err => {
        console.error('Failed to copy: ', err);
        alert('Failed to copy API key');
      });
  }

  // Функция для здаания начальных статусов APK кнопок
  async function prepareButton(button) {
    const apiKey = button.getAttribute("api-key");
    const row = button.closest("tr");

    // Показываем временный "лоадер" пока идёт запрос
    setButtonLoading(button, "Проверяем статус");
    const status = await checkBuildStatus(apiKey);

    if (status === "pending") {
      updateButton(button, "На сборке", STATUSES.create);
      pollBuildStatus(apiKey, button, row);
    } else if (status === "success") {
      updateButton(button, "Скачать APK", STATUSES.ready);
    } else if (status === "failed") {
      updateButton(button, "Повторить сборку", STATUSES.failed);
      if (firstAlert) {
        firstAlert = false;
        alert("⚠️ У вас есть неудачные сборки APK. Нажмите \"Повторить сборку\" для повторной попытки");
      }
    }
    // если ничего нет - считаем что билд не запускался
  }

// Функция для изменения статусов APK кнопок при нажатии
  async function changeAPKButtonState(button) {
    const apiKey = button.getAttribute("api-key");
    let btnStatus = button.getAttribute("data-status");
    let row = button.closest("tr");

    if (btnStatus === STATUSES.order || btnStatus === STATUSES.failed) {
      // Старт сборки
      const buildData = await startAPKBuild(apiKey);
      if (buildData?.apk_build_id) {
        updateButton(button, "На сборке", STATUSES.create);
        // Запускаем опрос статуса
        pollBuildStatus(apiKey, button, row);
      }
    } else if (btnStatus === STATUSES.create) {
      // Ручная проверка статуса сборки
      clearInterval(button._pollInterval);
      button._pollInterval = null;
      clearButtonLoading(button);

      button.disabled = true;
      button.textContent = "Проверяем статус...";

      const isReady = await checkBuildStatus(apiKey);

      if (isReady === "success") {
        updateButton(button, "Скачать APK", STATUSES.ready);
        clearInterval(button._pollInterval);
        button._pollInterval = null;
        clearButtonLoading(button);
        button.disabled = false;

      } else if (isReady === "failed") {
        alert("❌ Ошибка сборки.\nНажмите на кнопку, чтобы запустить заново.");
        updateButton(button, "Повторить сборку", STATUSES.failed);
        clearInterval(button._pollInterval);
        button._pollInterval = null;
        clearButtonLoading(button);
        button.disabled = false;

      } else {
        // Если все еще собирается
        setTimeout(() => {
          button.textContent = "Всё ещё собирается...";
        }, 2000);

        setTimeout(() => {
          button.disabled = false;
          pollBuildStatus(apiKey, button, row);
        }, 4000);

      }
    } else if (btnStatus === STATUSES.ready) {
      // Скачивание APK
      downloadAPK(apiKey);
    }
  }

  // Универсальное обновление кнопки
  function updateButton(button, text, status) {
    button.textContent = text;
    button.setAttribute("data-status", status);
  }

  // ЗАПРОСЫ НА СЕРВЕР 
  // Запрос на сборку APK на сревер
  async function startAPKBuild(apiKey) {
    try {
      const response = await fetch("http://localhost/api/apk/build/", {
        method: "POST",
        headers: {
          "Authorization": `Api-Key ${apiKey}`,
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken")
        }
      });

      if (!response.ok) throw new Error(`HTTP error: ${response.status}`);
      const data = await response.json();
      console.log("Build started:", data);
      alert("APK сборка началась!");
      return data;
    } catch (error) {
      console.error("Error:", error);
      alert("Ошибка при запуске сборки: " + error.message);
      return null;
    }
  }

/**
 * Проверяет статус сборки APK для указанного apiKey.
 *
 * Возвращаемые значения:
 *  - "pending" — сборка запущена, но ещё не завершена
 *  - "success" — сборка завершена успешно
 *  - "failed" — сборка завершилась с ошибкой
 *  - null — сборка ещё не запускалась (HTTP 404)
 *  - "error" — произошла ошибка запроса или сети
 *
 * NOTE: HTTP 404 не считается критической ошибкой. Это означает,
 * что для данного API ключа сборка ещё не создавалась, и обработка продолжается без alert.
 */
  async function checkBuildStatus(apiKey) {
    try {
      const response = await fetch("http://localhost/api/apk/build/", {
        method: "GET",
        headers: {
          "Authorization": `Api-Key ${apiKey}`,
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken")
        }
      });

      if (response.status === 404) {
        // сборка не запускалась
        return null;
      }

      if (!response.ok) throw new Error(`HTTP error: ${response.status}`);
      const data = await response.json();
      console.log("Build status:", data);

      if (data.completed_at) {
        return data.status;
      }
      return "pending";
    } catch (error) {
      console.error("Error checking status:", error);
      return "error";
    }
  }

  // Автоматический опрос каждые N секунд
  function pollBuildStatus(apiKey, button, row) {
    if (button._pollInterval) {
      clearInterval(button._pollInterval);
    }

    // Показываем мигающий текст пока статус pending
    setButtonLoading(button, "Собираем APK");
    const interval = setInterval(async () => {

      const status = await checkBuildStatus(apiKey);
      if (status === "success") {
        updateButton(button, "Скачать APK", STATUSES.ready);
        clearButtonLoading(button);
        clearInterval(interval);
      } else if (status === "failed") {
        alert("Ошибка сборки :(\nНажмите на кнопку с ошибкой, чтобы запустить заново")
        updateButton(button, "Повторить сборку", STATUSES.failed);
        clearInterval(interval);
        clearButtonLoading(button);
      }
    }, timeToCheck);

    button._pollInterval = interval;
  }

  // Функция для загрузки APK при клике на кнопку
  async function downloadAPK(apiKey) {
    try {
      const response = await fetch("http://localhost/api/apk/build/?action=download", {
        method: "GET",
        headers: {
          "Authorization": `Api-Key ${apiKey}`,
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken")
        }
      });

      if (!response.ok) throw new Error(`Download failed: ${response.status}`);
      const blob = await response.blob();

      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "app.apk";
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error("Download error:", error);
      alert("Ошибка при скачивании: " + error.message);
    }
  }

  // АНИМАЦИИ ДЛЯ КНОПКИ
  // Установка анимации с точкиами
  function setButtonLoading(button, baseText = "Обработка") {
    let dots = 0;
    // Останавливаем старый цикл, если он был
    if (button._loadingInterval) clearInterval(button._loadingInterval);

    button._loadingInterval = setInterval(() => {
      dots = (dots + 1) % 4;
      button.textContent = baseText + ".".repeat(dots);
    }, 1000);
  }
  
  // Удаление анимации с кнопки
  function clearButtonLoading(button, finalText) {
    if (button._loadingInterval) {
      clearInterval(button._loadingInterval);
      button._loadingInterval = null;
    }
    if (finalText) button.textContent = finalText;
  }
});

// Функция для удаления устройства
function deleteDevice(deviceId, deviceName) {
  if (confirm(`Are you sure you want to delete the device "${deviceName}"?`)) {
    fetch(`/api/api-key/${deviceId}/`, {
      method: 'DELETE',
      headers: {
        'X-CSRFToken': getCookie('csrftoken')
      }
    })
      .then(response => {
        if (response.ok) {
          alert('Device deleted successfully!');
          location.reload();
        } else {
          throw new Error('Failed to delete device');
        }
      })
      .catch(error => {
        console.error('Error:', error);
        alert('Error deleting device');
      });
  }
}

// Вспомогательная функция для получения CSRF токена
function getCookie(name) {
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
