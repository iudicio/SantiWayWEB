/* custom-elements.js
   В этом файле:
   - логика «кастомных select» (создание обёртки и списка опций)
   - логика меню столбцов таблицы (создание чекбоксов, скрыть/показать столбцы)
   - выделение строки таблицы и отображение выбранного Device ID
   - логика раскрывающихся списков: выделения всех элементов, заполнение новых чекбоксов
*/

document.addEventListener("DOMContentLoaded", ()=>{
  initCustomSelects();
  initColumnsMenu();
  initRowSelection();
  initCollapsibleList("apiList");
  initCollapsibleList("deviceList", true);
  initCollapsibleList("folderList", true);
})

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
function initCollapsibleList(id, disabled=false) {
  const container = document.getElementById(id);
  const wrapper = container.parentElement;
  const header = wrapper.querySelector(".collapsible-header");
  const selectAll = container.querySelector("input[value='__all__']");
  const status = header.querySelector(".selection-status")

  if (disabled) {
    setCollapsibleDisabled(id, disabled);
  }

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
    if (wrapper.classList.contains("disabled")) return;
    wrapper.classList.toggle("open");
  });
}

// Блокирует/разблокирует любой список
function setCollapsibleDisabled(id, disabled) {
  const container = document.getElementById(id);
  if (!container) return;

  const wrapper = container.parentElement;
  const header = wrapper.querySelector(".collapsible-header");

  if (disabled) {
    if (wrapper.classList.contains("open")) wrapper.classList.toggle("open");
    container.querySelector("input[value='__all__']").checked = false;
    wrapper.classList.add("disabled");
    header.querySelector(".selection-status").textContent = "Выбрано: 0";
  } else {
    wrapper.classList.remove("disabled");
  }
}

function fillCollapsibleList(id, elements, parents = null){
  const container = document.getElementById(id);
  if (!container) return;

  // Удаляем все чекбоксы, кроме "__all__"
  Array.from(container.querySelectorAll("input[type='checkbox']"))
    .forEach(cb => {
      if (cb.value !== "__all__") cb.closest("label").remove();
    });

  if (Array.isArray(elements)) {
    if (Array.isArray(parents)){
      elements.forEach((el, idx) => {
        const parent = parents[idx];
        container.appendChild(createCustomCheckbox(el, el, parent));
      });
    } else {
      elements.forEach((el) => {
        container.appendChild(createCustomCheckbox(el, el, parents));
      });
    }
  } else if (typeof elements === "object" && elements !== null) {
    // объект (API)
    Object.entries(elements).forEach(([key, label]) => {
      container.appendChild(createCustomCheckbox(key, label)); // parent не нужен
    });
  }
}

// Создает кастомные чекбоксы
function createCustomCheckbox(checkboxValue, labelText, dataParent=null){
  labelText = labelText ? labelText : checkboxValue;

  let label = document.createElement("label");
  label.classList = "custom-checkbox";

  let checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.value = checkboxValue;

  if (dataParent)
    checkbox.setAttribute("data-parent", dataParent);

  label.appendChild(checkbox);
  label.appendChild(document.createTextNode(labelText));

  return label
}

// Управляет логикой отображения списков
class CascadeController {
  constructor(structure, dataProvider) {
    this.structure = structure;
    this.dataProvider = dataProvider;
    this.state = {}; // выбранные значения
    this.cache = {};
  }

  init() {
    this.structure.forEach(level => {
      const container = document.getElementById(level.containerId);
      if (!container) return;
      container.addEventListener("change", () => {
        this.handleChange(level);
      });
    });
  }

  async handleChange(level) {
    const selected = this.getSelected(level.containerId);
    const prevSelected = this.state[level.id] || [];
    this.state[level.id] = selected;

    const nextLevel = this.getNextLevel(level.id);
    if (!nextLevel) return;
    const nextContainer = document.getElementById(nextLevel.containerId);

    // Обработка снятия выделения с чекбокса и удаляем “осиротевшие” элементы
    const removed = prevSelected.filter(x => !selected.includes(x));
    if (removed.length) {
      // удаляем потомков для снятых элементов
      if (removed.length === 1){
       this.removeChildren(level.id, removed[0]);
      } else {
        this.clearAllNextLists(level.id)
      }
    }

    // Добавление новых элементов
    const newlySelected = selected.filter(x => !prevSelected.includes(x));
    if (newlySelected.length === 0) return;

    const fragment = document.createDocumentFragment();
    for (const newSelect of newlySelected) {
      let data = [];

      if (level.id === "api" && nextLevel.id === "device") {
        if (this.cache[newSelect] && Object.keys(this.cache[newSelect]).length > 0) {
          console.log(`[CACHE] Devices for API ${newSelect} — from cache`);
          data = Object.keys(this.cache[newSelect]);
        } else {
          // для девайсов: передаём только новый API
          data = await this.dataProvider("device", { api: [newSelect] });

          // гарантируем, что у API есть место в кэше
          if (!this.cache[newSelect]) {
            this.cache[newSelect] = {};
          }

          data.forEach(device => {
            this.cache[newSelect][device] = [];
          })
        }
      } else if (level.id === "device" && nextLevel.id === "folder") {
        let foundInCache = false;
        Object.keys(this.cache).forEach(api => {
          if (this.cache[api]?.[newSelect]?.length > 0) {
            console.log(`[CACHE] Folders for device ${newSelect} from API ${api}`);
            data = this.cache[api][newSelect];
            foundInCache = true;
            break;
          }
        });

        if (!foundInCache) {
          // для папок: передаём новый девайс + все выбранные API
          data = await this.dataProvider("folder", {device: [newSelect], api: this.state["api"] ||  []});

          Object.keys(this.cache).forEach(api => {
            if (this.cache[api]?.[newSelect]) this.cache[api][newSelect] = data;
          })
        }
      }

      // добавляем новые элементы в список
      data.forEach((el) => {
        if (!nextContainer.querySelector(`input[value="${el}"][data-parent="${newSelect}"]`)) {
          fragment.appendChild(createCustomCheckbox(el, el, newSelect));
        }
      });
    }
    // Добавляем все за 1 раз
    nextContainer.appendChild(fragment);

    // Включаем список
    this.changeCollapsibleState(nextLevel.containerId);
  }

  // Рекурсивно удаляет элементы от верхних списков до нижних
  removeChildren(levelId, parentKey) {
    const levelIdx = this.structure.findIndex(l => l.id === levelId);
    const nextLevel = this.structure[levelIdx + 1];
    if (!nextLevel) return;

    const nextContainer = document.getElementById(nextLevel.containerId);

    // ищем детей исходя из уровня
    let children = [];

    if (levelId === "api") {
      // parentKey = имя API
      children = this.cache[parentKey] ? Object.keys(this.cache[parentKey]) : [];

    } else if (levelId === "device") {
      // parentKey = имя девайса; ищем в каком API он находится
      for (const api in this.cache) {
        if (this.cache[api]?.[parentKey]) {
          children = this.cache[api][parentKey];
          break;
        }
      }
    } else return;

    children.forEach(child => {
      const cb = nextContainer.querySelector(`input[data-parent="${parentKey}"]`);
      if (cb) cb.closest("label").remove();
      this.removeChildren(nextLevel.id, child); // рекурсивно удаляем потомков
    });

    // блокируем следующий уровень, если пусто
    this.changeCollapsibleState(nextLevel.containerId);

    // обновляем state
    this.state[nextLevel.id] = this.getSelected(nextLevel.containerId);
  }

  // Очищает все списки следующих уровней
  clearAllNextLists(levelId) {
    const idx = this.structure.findIndex(l => l.id === levelId);
    for (let i = idx + 1; i < this.structure.length; i++) {
      const child = this.structure[i];
      const container = document.getElementById(child.containerId);
      if (!container) continue;

      // Удаляем все чекбоксы, кроме "__all__"
      Array.from(container.querySelectorAll("input[type='checkbox']"))
        .forEach(cb => {
          if (cb.value !== "__all__") cb.closest("label").remove();
        });

      // Сбрасываем состояние
      this.state[child.id] = [];

      // Блокируем раскрытие
      setCollapsibleDisabled(child.containerId, true);
    }
  }

  // Определяет нужно ли сворачивать/раскрывать список
  changeCollapsibleState(nextLevelId){
    const hasChildren = document.getElementById(nextLevelId).querySelectorAll("input[type='checkbox']").length - 1 > 0;
    setCollapsibleDisabled(nextLevelId, !hasChildren);
  }

  // Возвращает id следующего списка
  getNextLevel(levelId) {
    const idx = this.structure.findIndex(l => l.id === levelId);
    return this.structure[idx + 1] || null;
  }

  // Получает все выбранные чекбоксы
  getSelected(containerId) {
    return Array.from(
      document.querySelectorAll(`#${containerId} input[type='checkbox']:checked`)
    ).filter(cb => cb.value !== "__all__").map(cb => cb.value);
  }
}


