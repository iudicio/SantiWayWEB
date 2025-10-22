document.addEventListener("DOMContentLoaded", () => {
  const STATUSES = { order: "order", create: "create", ready: "ready", failed: "failed" };
  const androidBtn = document.querySelectorAll(".apk-btn");
  const openModalBtn = document.getElementById('openModalBtn');
  const timeToCheck = 20000; // Запрос к серверу каждые 20 секунд
  let firstAlert = true;
  const APK_URL = "/api/apk/build/";
  const API_URL = "/api/api-key/";


  // Вешаем функцию создания апи ключа на кнопку
  if (openModalBtn) {
    openModalBtn.addEventListener('click', function () {
      // Используем prompt для ввода названия ключа
      let modal = showModal({
        title: "Создание API-ключа",
        body: `
          <div class="form-group">
            <label for="apiName">Название API-ключа:</label>
            <input type="text" id="apiName" placeholder="Введите название API-ключа" value="My API Key">
            <div class="error" id="apiError"></div>
          </div>
        `,
        footer: "<button class='btn-primary'>Создать</button>",
        onOpen: (overlay) => {
          const apiName = overlay.querySelector('#apiName');
          const error = overlay.querySelector('#apiError');
          const btnOk = overlay.querySelector('.btn-primary');

          apiName.focus();
          apiName.select();

          // Реакция на ввод
          apiName.addEventListener('input', () => {
            if (apiName.value.trim()) {
              error.textContent = '';
              btnOk.disabled = false;
            } else {
              error.textContent = 'Поле не может быть пустым';
              btnOk.disabled = true;
            }
          });

          apiName.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
              btnOk.click();
            }
          });

          // Обработчики кнопок
          btnOk.addEventListener('click', () => {
            if (!apiName.value.trim()) return (error.textContent = 'Поле не может быть пустым');
            createApiKey(apiName.value.trim())
            modal.close();
          });
        }
      })
    });
  }

  // Для уже созданных элементов проходимся и вешаем обработчики
  androidBtn.forEach(button => {
    prepareButton(button);
    button.addEventListener("click", () => { changeAPKButtonState(button) });
    clearButtonLoading(button);
  })

  document.querySelectorAll(".mono").forEach(el => {
    el.addEventListener("click", () => { copyApiKey(el) });
  });

  // Функция для создания API ключа
  function createApiKey(name) {
    console.log('Creating API key with name:', name);

    // Отправляем POST запрос на сервер
    fetch(API_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCookie('csrftoken')
      },
      body: JSON.stringify({ name })
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
        // Ожидаем формат: { key_id, api_key, name, created_at }
        // Небольшая защита, если бэк по старому отдаёт device_name:
        const keyId = data.key_id || data.id;
        const keyName = data.name || data.device_name || 'Без названия';
        const keyValue = data.api_key;
        const createdAt = (data.created_at || new Date().toISOString()).split("T")[0];
        // Показываем пользователю созданный API ключ
         showModal({
          title: "API-ключ успешно создан!",
          body: `
            <div class="modal-info">
              <p><strong>Device:</strong> ${keyName}</p>
              <p><strong>API-ключ:</strong> <span class="mono">${keyValue}</span></p>
            </div>
          `,
        });
        console.log("Data: ", data);
        addNewApiKeyRow(keyName, keyValue, keyId, createdAt);
      })
      .catch(error => {
        console.error('Error:', error);
        alert('Error: ' + error.message);
      });
  }

  function addNewApiKeyRow(apiName, apiKey, apiId, created_at) {
    const tbody = document.querySelector('#devicesTable tbody');

    // Убираем "Нет созданных API ключей"
    if (tbody.querySelector('td[colspan]')) {
      tbody.innerHTML = '';
    }

    // Создаем элементы вручную
    const tr = document.createElement('tr');

    // Название устройства
    const tdName = document.createElement('td');
    tdName.textContent = apiName;

    // API ключ
    const tdKey = document.createElement('td');
    const pKey = document.createElement('p');
    pKey.className = 'mono';
    pKey.textContent = apiKey;
    pKey.setAttribute("data-key-id", apiId)
    pKey.addEventListener("click", () => { copyApiKey(pKey) });
    tdKey.appendChild(pKey);

    // Дата создания
    const tdDate = document.createElement('td');
    tdDate.className = 'text-center';
    tdDate.textContent = created_at;

    // Кнопка APK
    const tdApk = document.createElement('td');
    tdApk.className = 'text-center';
    const apkBtn = document.createElement('button');
    apkBtn.className = 'apk-btn btn-primary';
    apkBtn.textContent = 'Собрать APK';
    apkBtn.setAttribute("data-status", STATUSES.order);
    apkBtn.setAttribute("data-api-key", apiKey);
    tdApk.appendChild(apkBtn);
    apkBtn.addEventListener("click", () => { changeAPKButtonState(apkBtn) });

    // Кнопка удаления
    const tdDelete = document.createElement('td');
    tdDelete.className = 'delete-column';
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'remove-btn delete-btn';
    deleteBtn.innerHTML = '&#10005;';
    deleteBtn.onclick = function () { deleteDevice(apiId, apiName); };
    tdDelete.appendChild(deleteBtn);

    // Собираем строку
    tr.appendChild(tdName);
    tr.appendChild(tdKey);
    tr.appendChild(tdDate);
    tr.appendChild(tdApk);
    tr.appendChild(tdDelete);

    // Добавляем в таблицу
    tbody.appendChild(tr);
  }

  // Анимация для копирования API-ключа
  function copyApiKey(element) {
    const original = element.textContent;
    if (original.trim() === "Скопировано!") return;

    // Делаем через современный способ
    if (navigator.clipboard){
      navigator.clipboard.writeText(original)
        .then(() => {
         apiKeyCopyAnimation(element, original);
        })
        .catch(err => {
          console.error('Ошибка копирования API-ключа: ', err);
          alert('Ошибка копирования API ключа');
        });
      return
    }

    // Если не помогло - классика
    const textarea = document.createElement('textarea');
    textarea.value = element.textContent;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    const successful = document.execCommand('copy');
    document.body.removeChild(textarea);

    if (successful) {
      apiKeyCopyAnimation(element, original);
    }
  }

  // Анимация текста на "скопировано" и обратно
  function apiKeyCopyAnimation(element, originalText){
    element.textContent = 'Скопировано!';
    element.classList.add("copied");
    setTimeout(() => {
      element.classList.remove("copied");
      element.textContent = originalText
    }, 1500);
  }

  // Функция для здаания начальных статусов APK кнопок
  async function prepareButton(button) {
    const apiKey = button.getAttribute("data-api-key");

    // Показываем временный "лоадер" пока идёт запрос
    setButtonLoading(button, "Проверяем статус");
    const status = await checkBuildStatus(apiKey);

    if (status === "pending") {
      updateButton(button, "На сборке", STATUSES.create);
      pollBuildStatus(apiKey, button);
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
    const apiKey = button.getAttribute("data-api-key");
    let btnStatus = button.getAttribute("data-status");

    if (btnStatus === STATUSES.order || btnStatus === STATUSES.failed) {
      // Старт сборки
      const buildData = await startAPKBuild(apiKey);
      if (buildData?.apk_build_id) {
        updateButton(button, "На сборке", STATUSES.create);
        // Запускаем опрос статуса
        pollBuildStatus(apiKey, button);
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
          pollBuildStatus(apiKey, button);
        }, 4000);

      }
    } else if (btnStatus === STATUSES.ready) {
      // Скачивание APK
      downloadAPK(apiKey, button);
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
      const response = await fetch(APK_URL, {
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
      const response = await fetch(APK_URL, {
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
  function pollBuildStatus(apiKey, button) {
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
  async function downloadAPK(apiKey, button = null) {
    const startTime = performance.now(); // время начала функции

    // Анимация - заглушка на всякий случай
    if (button){
      button.disabled = true;
      setButtonLoading(button, "Загрузка");
    }

    try {
      const response = await fetch(`${APK_URL}?action=download`, {
        method: "GET",
        headers: {
          "Authorization": `Api-Key ${apiKey}`,
          "Content-Type": "application/json",
          "X-CSRFToken": getCookie("csrftoken")
        }
      });

      console.log('Fetch completed', performance.now() - startTime, 'ms');
      if (!response.ok) throw new Error(`Download failed: ${response.status}`);
      const blob = await response.blob();
      console.log('Blob created', performance.now() - startTime, 'ms');

      const url = window.URL.createObjectURL(blob);
      console.log('Object URL created', performance.now() - startTime, 'ms');

      const a = document.createElement("a");
      a.href = url;
      a.download = "app.apk";
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      console.log('Download triggered', performance.now() - startTime, 'ms');

    } catch (error) {
      console.error("Download error:", error);
      alert("Ошибка при скачивании: " + error.message);
    } finally {
      if (button){
        clearButtonLoading(button, "Скачать APK");
        button.disabled = false;
      }
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
function deleteDevice(keyId, keyName) {
  if (confirm(`Are you sure you want to delete the device "${keyName}"?`)) {
    fetch(`/api/api-key/${keyId}/`, {
      method: 'DELETE',
      headers: {
        'X-CSRFToken': getCookie('csrftoken')
      }
    })
      .then(response => {
        if (response.ok) {
          alert('Device deleted successfully!');
          removeApiKeyFromTable(keyId)
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

// Удаление строки из таблицы
function removeApiKeyFromTable(keyId){
  const row = document.querySelector(`[data-key-id="${keyId}"]`).closest("tr");
  row.remove()
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
