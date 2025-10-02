/* scripts.js
   В этом файле:
   - логика «кастомных select» (создание обёртки и списка опций)
   - логика меню столбцов таблицы (создание чекбоксов, скрыть/показать столбцы)
   - выделение строки таблицы и отображение выбранного Device ID
   ---
   Важно: если у тебя есть app.js / generatedata.js, они подключаются ДО этого скрипта.
*/

document.addEventListener("DOMContentLoaded", ()=>{
  /**
   * Инициализация кастомных селектов: оборачивает каждый <select class="custom-select">
   * в видимую кастомную реализацию. Не оборачивает, если уже обёрнут.
   */
  initCustomSelects();
  initColumnsMenu();
  initRowSelection();

  function initCustomSelects() {
    document.querySelectorAll("select.custom-select").forEach(select => {
      // не повторно оборачиваем
      if (select.dataset.wrapped === "true") return;

      // создаём wrapper
      const wrapper = document.createElement("div");
      wrapper.className = "custom-select-wrapper";

      // отображаем выбранное
      const display = document.createElement("div");
      display.className = "custom-select-display";
      display.tabIndex = 0;
      const selectedText = select.options[select.selectedIndex]?.text || "Выберите";
      display.textContent = selectedText;

      // список опций
      const options = document.createElement("div");
      options.className = "custom-select-options";

      Array.from(select.options).forEach(opt => {
        const optionDiv = document.createElement("div");
        optionDiv.textContent = opt.text;
        optionDiv.dataset.value = opt.value;

        optionDiv.addEventListener("click", () => {
          select.value = opt.value;
          // обновим отображение
          display.textContent = opt.text;
          options.classList.remove("open");
          display.classList.remove("open");
          // при необходимости триггерим событие изменения нативного select
          select.dispatchEvent(new Event("change", { bubbles: true }));
        });

        options.appendChild(optionDiv);
      });

      // открытие/закрытие
      display.addEventListener("click", e => {
        e.stopPropagation();
        const isOpen = options.classList.toggle("open");
        display.classList.toggle("open", isOpen);
      });

      // клик вне — закрыть
      document.addEventListener("click", (e) => {
        if (!wrapper.contains(e.target)) {
          options.classList.remove("open");
          display.classList.remove("open");
        }
      });

      // Скрываем нативный select (CSS уже задан) и помечаем чтобы не оборачивать повторно
      select.style.display = "none";
      select.dataset.wrapped = "true";

      wrapper.appendChild(display);
      wrapper.appendChild(options);
      select.parentNode.insertBefore(wrapper, select);
    });
  }

  /**
   * Создание меню управления столбцами таблицы.
   * Работает с таблицей, имеющей id="devicesTable" и кнопкой id="columnsToggle" и контейнер id="columnsMenu".
   */
  function initColumnsMenu() {
    const table = document.getElementById("devicesTable");
    const toggleBtn = document.getElementById("columnsToggle");
    const menu = document.getElementById("columnsMenu");
    if (!table || !toggleBtn || !menu) return;

    // получаем th и навесим data-col (уникальные ключи)
    const ths = Array.from(table.querySelectorAll("thead th"));
    ths.forEach((th, idx) => {
      if (!th.dataset.col) th.dataset.col = "col" + idx;
    });

    // очистим меню и создадим элементы
    menu.innerHTML = "";
    ths.forEach(th => {
      const labelText = th.textContent.trim();
      const key = th.dataset.col;

      const wrapper = document.createElement("label");
      wrapper.style.display = "block";

      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.checked = th.style.display !== "none";
      cb.dataset.col = key;

      cb.addEventListener("change", () => {
        const colKey = cb.dataset.col;
        const thEl = table.querySelector(`thead th[data-col="${colKey}"]`);
        const tds = table.querySelectorAll(`tbody td[data-col="${colKey}"]`);

        if (!thEl) return;

        if (cb.checked) {
          thEl.style.display = "";
          tds.forEach(td => td.style.display = "");
        } else {
          thEl.style.display = "none";
          tds.forEach(td => td.style.display = "none");
        }
      });

      wrapper.appendChild(cb);
      wrapper.append(" " + labelText);
      menu.appendChild(wrapper);
    });

    // назначим data-col на существующие td (если строки уже есть)
    function syncRowTdDataCols() {
      const rows = table.querySelectorAll("tbody tr");
      rows.forEach(tr => {
        Array.from(tr.children).forEach((td, i) => {
          const th = ths[i];
          if (th) td.dataset.col = th.dataset.col;
        });
      });
    }
    syncRowTdDataCols();

    // переключатель меню
    toggleBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      menu.classList.toggle("hidden");
      const expanded = menu.classList.contains("hidden") ? "false" : "true";
      toggleBtn.setAttribute("aria-expanded", expanded);
    });

    // клик в документе — закрыть меню, если клик вне
    document.addEventListener("click", (e) => {
      if (!menu.contains(e.target) && e.target !== toggleBtn) {
        menu.classList.add("hidden");
        toggleBtn.setAttribute("aria-expanded", "false");
      }
    });

    // если строки будут добавляться позже (динамически), попытка синхронизировать data-col
    // Запускаем периодически в первые секунды — минимальная попытка без вмешательства в app.js
    let attempts = 0;
    const syncInterval = setInterval(() => {
      attempts++;
      syncRowTdDataCols();
      if (attempts > 20) clearInterval(syncInterval);
    }, 200);
  }

  /**
   * Обработчик клика по строке таблицы: выделить строку, показать Device ID в selected-id.
   * Используется делегирование — работает и для динамических строк.
   */
  function initRowSelection() {
    const table = document.getElementById("devicesTable");
    const selectedDisplay = document.getElementById("selected-id");
    if (!table || !selectedDisplay) return;

    const tbody = table.querySelector("tbody");
    if (!tbody) return;

    // делегирование
    tbody.addEventListener("click", (e) => {
      // найти ближайший tr
      const tr = e.target.closest("tr");
      if (!tr) return;

      const firstTd = tr.querySelector("td");
      const deviceId = firstTd ? firstTd.textContent.trim() : "";
      selectedDisplay.textContent = deviceId || "—";

      // убрать выделение у всех и добавить к текущей
      tbody.querySelectorAll("tr").forEach(r => r.classList.remove("highlighted"));
      tr.classList.add("highlighted");
    });
  }
});
