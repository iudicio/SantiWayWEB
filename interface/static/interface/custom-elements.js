/* scripts.js
   В этом файле:
   - логика «кастомных select» (создание обёртки и списка опций)
   - логика меню столбцов таблицы (создание чекбоксов, скрыть/показать столбцы)
   - выделение строки таблицы и отображение выбранного Device ID
   - логика раскрывающихся списков
*/

document.addEventListener("DOMContentLoaded", ()=>{
  initCustomSelects();
  initColumnsMenu();
  initRowSelection();
  initCollapsibleList("apiList");
  initCollapsibleList("deviceList");
  initCollapsibleList("folderList");


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
      display.textContent = select.options[select.selectedIndex]?.text || "Выберите";

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

//   Создание меню управления столбцами таблицы.
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
      // Создание чекбокса и его label
      const wrapper = document.createElement("label");
      wrapper.classList.add("custom-checkbox");

      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = th.style.display !== "none";
      checkbox.dataset.col = key;
      //    Обработка нажатие (скрыть/показать столбец)
      checkbox.addEventListener("change", () => {
        const colKey = checkbox.dataset.col;
        const thElement = table.querySelector(`thead th[data-col="${colKey}"]`);
        const tds = table.querySelectorAll(`tbody td[data-col="${colKey}"]`);

        if (!thElement) return;

        if (checkbox.checked) {
          thElement.style.display = "";
          tds.forEach(td => td.style.display = "");
        } else {
          thElement.style.display = "none";
          tds.forEach(td => td.style.display = "none");
        }
      });

      wrapper.appendChild(checkbox);
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
  }

//    Обработчик клика по строке таблицы: выделить строку, показать Device ID в selected-id.
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

//   Создание раскрывающегося списка apiList.
  function initCollapsibleList(id) {
    const container = document.getElementById(id);
    const wrapper = container.parentElement;
    const header = wrapper.querySelector(".collapsible-header");
    const selectAll = container.querySelector("input[value='__all__']");
    const status = header.querySelector(".selection-status");

    // обновление статуса при нажатии на selectAll-чекбокс
    function updateStatus() {
      const total = container.querySelectorAll("input[type='checkbox']").length - 1;
      const count = container.querySelectorAll("input[type='checkbox']:not([value='__all__']):checked").length;
      status.textContent = `Выбрано: ${count}`;
      selectAll.checked = (count === total);
      selectAll.indeterminate = (count > 0 && count < total);
    }

    // обработка кликов по чекбоксам
    container.addEventListener("change", (e) => {
      if (e.target.value === "__all__") {
        const allChecked = e.target.checked;
        container.querySelectorAll("input[type='checkbox']:not([value='__all__'])")
          .forEach(checkbox => checkbox.checked = allChecked);
      }
      updateStatus();
    });

    // Переключение по клику на header
    header.addEventListener("click", () => {
      wrapper.classList.toggle("open");
    });
  }
});
