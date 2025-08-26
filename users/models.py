import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser


class APIKey(models.Model):
    key = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.key)

class Device(models.Model):
    name = models.CharField(max_length=100)
    api_key = models.ForeignKey(APIKey, related_name='devices', on_delete=models.CASCADE)

    def __str__(self):
        return self.name

class SearchQuery(models.Model):
    query_text = models.TextField()
    filters = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.query_text

class User(AbstractUser):
    registration_date = models.DateTimeField(auto_now_add=True)
    api_keys = models.ManyToManyField(APIKey, blank=True)
    last_login_date = models.DateTimeField(null=True, blank=True)
    search_queries = models.ManyToManyField(SearchQuery, blank=True)

    def __str__(self):
        return self.username