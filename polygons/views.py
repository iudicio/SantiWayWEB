from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import action
from .models import Polygon, PolygonAction
from .serializers import PolygonSerializer, PolygonActionSerializer
from .utils import search_devices_in_polygon
from .tasks import monitor_mac_addresses, stop_polygon_monitoring, stop_all_polygon_actions
from api.auth import APIKeyAuthentication
from api.permissions import HasAPIKey
from users.models import User


class IsOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return getattr(obj, "user_id", None) == getattr(getattr(request, "user", None), "id", None)


class PolygonViewSet(viewsets.ModelViewSet):
    serializer_class = PolygonSerializer
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [HasAPIKey | permissions.IsAuthenticated]

    def get_user_from_request(self):
        """Получает пользователя из запроса (сессия или API ключ)"""
        # Если есть API ключ, получаем пользователя через связь
        if hasattr(self.request, 'auth') and self.request.auth:
            api_key = self.request.auth
            user = User.objects.filter(api_keys=api_key).first()
            if user:
                return user
        
        # Если есть аутентифицированный пользователь (сессия)
        if hasattr(self.request, 'user') and self.request.user.is_authenticated:
            return self.request.user
        
        return None

    def get_queryset(self):
        user = self.get_user_from_request()
        if user:
            return Polygon.objects.filter(user=user).order_by("-created_at")
        return Polygon.objects.none()

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request_user"] = self.get_user_from_request()
        return ctx

    def perform_create(self, serializer):
        user = self.get_user_from_request()
        if not user:
            raise PermissionDenied("Authentication required")
        serializer.save(user=user)

    def perform_update(self, serializer):
        instance = self.get_object()
        user = self.get_user_from_request()
        if not user:
            raise PermissionDenied("Authentication required")
        if instance.user_id != user.id:
            raise PermissionDenied("Not your polygon")
        serializer.save()

    def perform_destroy(self, instance):
        user = self.get_user_from_request()
        if not user:
            raise PermissionDenied("Authentication required")
        if instance.user_id != user.id:
            raise PermissionDenied("Not your polygon")
            
        stop_all_polygon_actions.delay(str(instance.id))
        
        instance.delete()

    @action(detail=True, methods=['post'])
    def search(self, request, pk=None):
        """Поиск устройств в полигоне"""
        polygon = self.get_object()
        
        try:
            api_key_str = None
            if hasattr(request, 'auth') and request.auth:
                api_key_str = str(request.auth.key)
            
            devices = search_devices_in_polygon(
                polygon.geometry, 
                user_api_key=api_key_str
            )
            return Response({
                'polygon_id': str(polygon.id),
                'polygon_name': polygon.name,
                'devices_found': len(devices),
                'devices': devices
            })
        except Exception as e:
            return Response(
                {'error': f'Ошибка поиска: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def start_monitoring(self, request, pk=None):
        """Запуск мониторинга MAC адресов в полигоне"""
        polygon = self.get_object()

        from django.db import transaction, IntegrityError
        from django.utils import timezone as dj_tz

        try:
            api_key_str = None
            if hasattr(request, 'auth') and request.auth:
                api_key_str = str(request.auth.key)

            monitoring_interval = request.data.get('monitoring_interval', 300)
            notify_targets = request.data.get('notify_targets', [])

            with transaction.atomic():
                existing_action = (
                    PolygonAction.objects.select_for_update()
                    .filter(polygon=polygon, action_type='mac_monitoring', status__in=['running', 'pending'])
                    .order_by('-created_at')
                    .first()
                )
                if existing_action:
                    return Response({
                        'error': 'Мониторинг уже запущен для этого полигона',
                        'action_id': str(existing_action.id)
                    }, status=status.HTTP_400_BAD_REQUEST)

                action = PolygonAction.objects.create(
                    polygon=polygon,
                    action_type='mac_monitoring',
                    parameters={
                        'monitoring_interval': monitoring_interval,
                        'user_api_key': api_key_str,
                        'notify_targets': notify_targets,
                    },
                    status='running',
                    started_at=dj_tz.now()
                )

            task = monitor_mac_addresses.delay(
                str(polygon.id),
                api_key_str,
                monitoring_interval
            )
            action.task_id = task.id
            action.save(update_fields=['task_id'])

            return Response({
                'message': 'Мониторинг MAC адресов запущен',
                'polygon_id': str(polygon.id),
                'polygon_name': polygon.name,
                'task_id': task.id,
                'monitoring_interval': monitoring_interval,
                'action_id': str(action.id)
            })

        except Exception as e:
            return Response(
                {'error': f'Ошибка запуска мониторинга: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=True, methods=['post'])
    def stop_monitoring(self, request, pk=None):
        """Остановка мониторинга MAC адресов в полигоне"""
        polygon = self.get_object()
        from django.utils import timezone as dj_tz

        try:
            active_actions = PolygonAction.objects.filter(
                polygon=polygon,
                action_type='mac_monitoring',
                status__in=['running', 'pending']
            )

            if not active_actions.exists():
                return Response({
                    'message': 'Мониторинг не запущен для этого полигона',
                    'polygon_id': str(polygon.id),
                    'polygon_name': polygon.name
                }, status=status.HTTP_400_BAD_REQUEST)

            stop_polygon_monitoring.delay(str(polygon.id))

            active_actions.update(status='stopped', completed_at=dj_tz.now())

            return Response({
                'message': 'Мониторинг MAC адресов остановлен',
                'polygon_id': str(polygon.id),
                'polygon_name': polygon.name
            })

        except Exception as e:
            return Response(
                {'error': f'Ошибка остановки мониторинга: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


    @action(detail=True, methods=['get'])
    def monitoring_status(self, request, pk=None):
        """Получение статуса мониторинга для полигона"""
        polygon = self.get_object()
        
        try:
            actions = PolygonAction.objects.filter(
                polygon=polygon,
                action_type='mac_monitoring'
            ).order_by('-created_at')
            
            if not actions.exists():
                return Response({
                    'polygon_id': str(polygon.id),
                    'polygon_name': polygon.name,
                    'monitoring_status': 'not_started',
                    'actions': []
                })
            
            serializer = PolygonActionSerializer(actions, many=True)
            
            running_actions = actions.filter(status='running')
            if running_actions.exists():
                monitoring_status = 'running'
            elif actions.filter(status='completed').exists():
                monitoring_status = 'completed'
            elif actions.filter(status='stopped').exists():
                monitoring_status = 'stopped'
            else:
                monitoring_status = 'unknown'
            
            return Response({
                'polygon_id': str(polygon.id),
                'polygon_name': polygon.name,
                'monitoring_status': monitoring_status,
                'actions': serializer.data
            })
            
        except Exception as e:
            return Response(
                {'error': f'Ошибка получения статуса: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
