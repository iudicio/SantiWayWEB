from django.shortcuts import render
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import action
from .models import Polygon, PolygonAction, AnomalyDetection, Notification, NotificationTarget
from .serializers import (PolygonSerializer, PolygonActionSerializer, PolygonActionWithTargetsSerializer,
                         AnomalyDetectionSerializer, NotificationSerializer, NotificationTargetSerializer)
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
            
            valid_target_types = ['api_key', 'device', 'email', 'webhook']
            for target in notify_targets:
                if target.get('target_type') not in valid_target_types:
                    return Response({
                        'error': f"Недопустимый тип цели: {target.get('target_type')}"
                    }, status=status.HTTP_400_BAD_REQUEST)

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
                
                for target_data in notify_targets:
                    NotificationTarget.objects.create(
                        polygon_action=action,
                        target_type=target_data['target_type'],
                        target_value=target_data['target_value'],
                        is_active=target_data.get('is_active', True)
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


class AnomalyDetectionViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для просмотра обнаруженных аномалий"""
    serializer_class = AnomalyDetectionSerializer
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [HasAPIKey | permissions.IsAuthenticated]

    def get_user_from_request(self):
        """Получает пользователя из запроса (сессия или API ключ)"""
        if hasattr(self.request, 'auth') and self.request.auth:
            api_key = self.request.auth
            user = User.objects.filter(api_keys=api_key).first()
            if user:
                return user
        
        if hasattr(self.request, 'user') and self.request.user.is_authenticated:
            return self.request.user
        
        return None

    def get_queryset(self):
        user = self.get_user_from_request()
        if user:
            return AnomalyDetection.objects.filter(
                polygon_action__polygon__user=user
            ).select_related(
                'polygon_action__polygon'
            ).order_by('-detected_at')
        return AnomalyDetection.objects.none()

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        """Отметить аномалию как решенную"""
        anomaly = self.get_object()
        user = self.get_user_from_request()
        
        if not user:
            raise PermissionDenied("Authentication required")
        
        anomaly.resolve(user=user)
        
        return Response({
            'message': 'Аномалия отмечена как решенная',
            'anomaly_id': str(anomaly.id),
            'resolved_at': anomaly.resolved_at,
            'resolved_by': user.username
        })

    def list(self, request, *args, **kwargs):
        """Список аномалий с фильтрацией"""
        queryset = self.get_queryset()
        
        severity = request.query_params.get('severity')
        anomaly_type = request.query_params.get('anomaly_type')
        is_resolved = request.query_params.get('is_resolved')
        polygon_id = request.query_params.get('polygon_id')
        
        if severity:
            queryset = queryset.filter(severity=severity)
        if anomaly_type:
            queryset = queryset.filter(anomaly_type=anomaly_type)
        if is_resolved is not None:
            queryset = queryset.filter(is_resolved=is_resolved.lower() == 'true')
        if polygon_id:
            queryset = queryset.filter(polygon_action__polygon_id=polygon_id)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class NotificationViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet для просмотра уведомлений"""
    serializer_class = NotificationSerializer
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [HasAPIKey | permissions.IsAuthenticated]

    def get_user_from_request(self):
        """Получает пользователя из запроса (сессия или API ключ)"""
        if hasattr(self.request, 'auth') and self.request.auth:
            api_key = self.request.auth
            user = User.objects.filter(api_keys=api_key).first()
            if user:
                return user
        
        if hasattr(self.request, 'user') and self.request.user.is_authenticated:
            return self.request.user
        
        return None

    def get_queryset(self):
        user = self.get_user_from_request()
        if user:
            return Notification.objects.filter(
                anomaly__polygon_action__polygon__user=user
            ).select_related(
                'anomaly__polygon_action__polygon',
                'target'
            ).order_by('-created_at')
        return Notification.objects.none()

    @action(detail=True, methods=['post'])
    def mark_as_read(self, request, pk=None):
        """Отметить уведомление как прочитанное"""
        notification = self.get_object()
        notification.mark_as_read()
        
        return Response({
            'message': 'Уведомление отмечено как прочитанное',
            'notification_id': str(notification.id),
            'read_at': notification.read_at
        })

    def list(self, request, *args, **kwargs):
        """Список уведомлений с фильтрацией"""
        queryset = self.get_queryset()
        
        # Фильтры
        status_filter = request.query_params.get('status')
        severity = request.query_params.get('severity')
        polygon_id = request.query_params.get('polygon_id')
        unread_only = request.query_params.get('unread_only')
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        if severity:
            queryset = queryset.filter(anomaly__severity=severity)
        if polygon_id:
            queryset = queryset.filter(anomaly__polygon_action__polygon_id=polygon_id)
        if unread_only and unread_only.lower() == 'true':
            queryset = queryset.filter(status__in=['pending', 'sent', 'delivered'])
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        """Получить количество непрочитанных уведомлений"""
        queryset = self.get_queryset()
        unread_count = queryset.filter(status__in=['pending', 'sent', 'delivered']).count()
        
        return Response({
            'unread_count': unread_count
        })


class NotificationTargetViewSet(viewsets.ModelViewSet):
    """ViewSet для управления целями уведомлений"""
    serializer_class = NotificationTargetSerializer
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [HasAPIKey | permissions.IsAuthenticated]

    def get_user_from_request(self):
        """Получает пользователя из запроса (сессия или API ключ)"""
        if hasattr(self.request, 'auth') and self.request.auth:
            api_key = self.request.auth
            user = User.objects.filter(api_keys=api_key).first()
            if user:
                return user
        
        if hasattr(self.request, 'user') and self.request.user.is_authenticated:
            return self.request.user
        
        return None

    def get_queryset(self):
        user = self.get_user_from_request()
        if user:
            return NotificationTarget.objects.filter(
                polygon_action__polygon__user=user
            ).select_related('polygon_action__polygon')
        return NotificationTarget.objects.none()

    def perform_create(self, serializer):
        polygon_action = serializer.validated_data['polygon_action']
        user = self.get_user_from_request()
        
        if not user:
            raise PermissionDenied("Authentication required")
        
        if polygon_action.polygon.user != user:
            raise PermissionDenied("Not your polygon action")
        
        serializer.save()

    def perform_update(self, serializer):
        instance = self.get_object()
        user = self.get_user_from_request()
        
        if not user:
            raise PermissionDenied("Authentication required")
        
        if instance.polygon_action.polygon.user != user:
            raise PermissionDenied("Not your notification target")
        
        serializer.save()

    def perform_destroy(self, instance):
        user = self.get_user_from_request()
        
        if not user:
            raise PermissionDenied("Authentication required")
        
        if instance.polygon_action.polygon.user != user:
            raise PermissionDenied("Not your notification target")
        
        instance.delete()
