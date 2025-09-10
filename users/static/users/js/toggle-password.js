document.addEventListener('DOMContentLoaded', function() {
    const toggleButton = document.getElementById('togglePassword');
    const passwordInput = document.getElementById('password');

    if (toggleButton && passwordInput) {
        toggleButton.addEventListener('click', function() {
            // Переключаем тип поля
            const type = passwordInput.getAttribute('type') === 'password' ? 'text' : 'password';
            passwordInput.setAttribute('type', type);

            // Переключаем класс для смены иконки
            toggleButton.classList.toggle('showing');

            // Меняем aria-label для доступности
            const label = type === 'password' ? 'Показать пароль' : 'Скрыть пароль';
            toggleButton.setAttribute('aria-label', label);
        });
    }
});