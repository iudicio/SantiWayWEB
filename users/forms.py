from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError

from .models import User


class RegistrationForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Отключение валидации имени пользователя
        self.fields["username"].validators = []
        # Кастомизация стандартных ошибки
        self.fields["email"].error_messages = {
            "invalid": "Введите корректный email адрес.",
            "required": "Обязательное поле.",
        }

    username = forms.CharField(
        required=True,
        widget=forms.TextInput(
            attrs={
                "class": "input-field",
                "placeholder": "Имя пользователя",
                "id": "username",
                "required": True,
            }
        ),
        label="Имя пользователя",
    )

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(
            attrs={
                "class": "input-field",
                "placeholder": "Email",
                "id": "email",
                "required": True,
            }
        ),
        label="Email",
    )

    password1 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "input-field",
                "placeholder": "Введите пароль",
                "id": "password",
                "required": True,
            }
        ),
        label="Пароль",
    )

    password2 = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "input-field",
                "placeholder": "Повторите пароль",
                "id": "repeat-password",
                "required": True,
            }
        ),
        label="Подтверждение пароля",
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def clean_email(self):
        email = self.cleaned_data.get("email").lower().strip()
        if User.objects.filter(email=email).exists():
            raise ValidationError("Пользователь с таким email уже существует.")
        return email

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if not username:
            raise ValidationError("Имя пользователя обязательно.")
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        # Явно сохраняем username
        user.username = self.cleaned_data["username"]
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    username = forms.EmailField(
        widget=forms.EmailInput(
            attrs={
                "class": "input-field",
                "placeholder": "Email",
                "id": "email",
            }
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "input-field",
                "placeholder": "Пароль",
                "id": "password",
            }
        )
    )
