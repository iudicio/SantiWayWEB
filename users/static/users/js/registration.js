document.addEventListener('DOMContentLoaded', () => {
    const passwordInput = document.getElementById("password");
    const repeatPasswordInput = document.getElementById("repeat-password");
    const emailInput = document.getElementById("email");
    const form = document.querySelector('.form');

    // Валидация пароля
    passwordInput.addEventListener("input", validatePassword);

    // Проверка совпадения паролей
    repeatPasswordInput.addEventListener("input", validatePasswordMatch);


    // Обработка отправки формы
    form.addEventListener("submit", (e) => {
        if (anyInputEmpty()) {
            alert("Заполните все поля");
            e.preventDefault();
            return;
        }
        if (!validatePassword()) {
            alert("Пароль должен содержать не менее 8 символов, включая цифры и буквы");
            e.preventDefault();
            return;
        }
        if (!validatePasswordMatch()) {
            alert("Пароли не совпадают");
            e.preventDefault();
            return;
        }
        console.log('Регистрация успешна!');
        
    });

    
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

    function anyInputEmpty() {
        const inputs = document.querySelectorAll('.input-field');
        for (let input of inputs) {
            if (input.value.trim() === "") {
                return true;
            }
        }
        return false;
    }
});