document.addEventListener('DOMContentLoaded', () => {
    const passwordInput = document.getElementById("password");
    const repeatPasswordInput = document.getElementById("repeat-password");

    // Валидация пароля
    passwordInput.addEventListener("input", validatePassword);

    // Проверка совпадения паролей
    repeatPasswordInput.addEventListener("input", validatePasswordMatch);

    function validatePassword() {
        const password = passwordInput.value;
        const regex = /^(?=.*[A-Za-z])(?=.*\d).{8,}$/;
        const isValid = regex.test(password);
        passwordInput.style.borderColor = isValid ? 'green' : 'red';
        return isValid;
    }

    function validatePasswordMatch() {
        const password = passwordInput.value;
        const repeatPassword = repeatPasswordInput.value;
        const isValid = password === repeatPassword && password !== '';
        repeatPasswordInput.style.borderColor = isValid ? 'green' : 'red';
        return isValid;
    }
});