/**
 * Создаёт модальное окно.
 *
 * @param {Object} options - Опции модального окна.
 * @param {string} [options.title=""] - Заголовок модалки.
 * @param {string} [options.body=""] - HTML-код основной части модалки.
 * @param {string} [options.footer=""] - HTML-код нижней части (кнопки). Если не указан, создаётся кнопка "Ок", закрывающая модалку.
 * @param {function} [options.onOpen=null] - Функция, вызываемая после рендера модалки. Используется для навешивания обработчиков на поля формы.
 *
 * @returns {Object} Объект с элементом overlay и функцией close:
 *   - overlay {HTMLElement} — сам overlay модалки.
 *   - close {function} — функция для закрытия модалки.
 *
 * @requires modal.css — для корректного отображения модалки необходим базовый набор стилей (overlay, modal, header, body, footer).
 */

function showModal({
    title = "",
    body = "",
    footer = "",
   onOpen = null
                   } = {}) {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay show";
  overlay.innerHTML = `
    <div class="modal">
      <div class="modal-header">
        <h3 class="modal-title">${title}</h3>
        <button class="modal-close">&#10005</button>
      </div>
      <div class="modal-body">${body}</div>
      <div class="modal-footer">${footer ? footer : "<button class='btn-primary'>Ок</button>"}</div>
    </div>
  `

  document.body.appendChild(overlay);

  const close = () => {
    overlay.classList.remove("show");
    overlay.remove();
  };

  const closeBtn = overlay.querySelector(".modal-close");
  if (closeBtn) closeBtn.addEventListener("click", close);

  // вызывать onOpen, чтобы можно было повесить обработчики после рендеринга
  if (typeof onOpen === 'function') onOpen(overlay);

  if (!footer){
    const okBtn = overlay.querySelector(".btn-primary");
    okBtn.focus();
    okBtn.addEventListener("click",  close);
  }

  let isDragging = false;
  overlay.addEventListener("mousedown", (e) => {
    // если клик начался внутри модалки — значит, пользователь что-то выделяет
    if (!e.target.closest(".modal")) return;
    isDragging = true;
  });

  overlay.addEventListener("mouseup", () => {
    // если мышь ушла за пределы — сбрасываем
    setTimeout(() => (isDragging = false), 0);
  });

  overlay.addEventListener("click", (e) => {
    // Закрываем только если клик не был частью выделения и был по фону
    if (isDragging) return;
    if (e.target === overlay) close();
  });

  return { overlay, close };
}