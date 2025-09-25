import uuid
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth.models import AnonymousUser
from users.models import APIKey

class APIKeyAuthentication(BaseAuthentication):
    keyword = b"api-key"

    def authenticate(self, request):
        # 1) Authorization: Api-Key <uuid>
        auth = get_authorization_header(request)
        key = None
        if auth:
            parts = auth.split()
            if len(parts) == 2 and parts[0].lower() == self.keyword:
                key = parts[1].decode()

        # 2) X-API-Key: <uuid>
        if not key:
            key = request.META.get("HTTP_X_API_KEY")

        if not key:
            return None  # позволяем сработать другим схемам, если они есть

        try:
            uuid_key = uuid.UUID(key)
        except ValueError:
            raise AuthenticationFailed("Invalid API key format.")

        api_key_obj = APIKey.objects.filter(key=uuid_key).first()
        if not api_key_obj:
            raise AuthenticationFailed("Invalid API key.")

        return (AnonymousUser(), api_key_obj)
