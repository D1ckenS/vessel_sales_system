"""
User API Views
Provides REST API endpoints for user management with vessel assignments and permissions.
"""

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django_filters.rest_framework import DjangoFilterBackend
from django.contrib.auth.models import User, Group
from django.db.models import Q, Count, Sum, F

from api.serializers.user_serializers import (
    UserSerializer,
    UserDetailSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    UserPasswordChangeSerializer,
    UserProfileSerializer,
    UserSummarySerializer,
    GroupSerializer
)


class GroupViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for user groups (read-only).
    
    Provides read access to user groups for permission management.
    """
    
    queryset = Group.objects.all().order_by('name')
    serializer_class = GroupSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['name', 'id']
    ordering = ['name']


class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for user management.
    
    Provides CRUD operations for users with permission management.
    """
    
    queryset = User.objects.select_related().prefetch_related('groups').all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'is_staff', 'is_superuser']
    search_fields = ['username', 'first_name', 'last_name', 'email']
    ordering_fields = ['username', 'date_joined', 'last_login']
    ordering = ['username']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == 'retrieve':
            return UserDetailSerializer
        elif self.action == 'create':
            return UserCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        elif self.action == 'change_password':
            return UserPasswordChangeSerializer
        elif self.action == 'profile':
            return UserProfileSerializer
        elif self.action == 'summary':
            return UserSummarySerializer
        return UserSerializer
    
    def get_permissions(self):
        """
        Set permission classes based on action.
        
        Only admin users can create, update, or delete users.
        Regular users can view their own profile.
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            permission_classes = [IsAdminUser]
        elif self.action in ['list', 'retrieve']:
            # Users can list/view all users but with limited info
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [IsAuthenticated]
        
        return [permission() for permission in permission_classes]
    
    def get_queryset(self):
        """Filter queryset based on user permissions."""
        queryset = super().get_queryset()
        
        # Non-admin users see limited user list
        if not self.request.user.is_staff and not self.request.user.is_superuser:
            # Regular users can only see active users (limited fields)
            queryset = queryset.filter(is_active=True)
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def profile(self, request):
        """
        Get current user's profile information.
        
        Returns detailed profile for the authenticated user.
        """
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def change_password(self, request):
        """
        Change current user's password.
        
        Requires old password verification.
        """
        serializer = self.get_serializer(data=request.data, context={'request': request})
        
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Password changed successfully.'
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """
        Get user summary for dropdowns and references.
        
        Returns minimal user data suitable for form dropdowns.
        """
        queryset = self.filter_queryset(self.get_queryset())
        
        # Only return active users for summary unless explicitly requested
        if not request.query_params.get('include_inactive'):
            queryset = queryset.filter(is_active=True)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['get'])
    def activity_summary(self, request, pk=None):
        """
        Get activity summary for a specific user.
        
        Returns transaction counts and activity statistics.
        """
        user = self.get_object()
        
        from datetime import datetime, timedelta
        
        # Get date range from parameters
        days = int(request.query_params.get('days', 30))
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        
        # Get transaction statistics
        transactions = user.transaction.filter(
            transaction_date__gte=start_date,
            transaction_date__lte=end_date
        )
        
        # Calculate activity summary
        activity_by_type = transactions.values('transaction_type').annotate(
            count=Count('id'),
            total_quantity=Sum('quantity'),
            total_amount=Sum(F('quantity') * F('unit_price'))
        )
        
        # Get activity by vessel
        activity_by_vessel = transactions.values(
            'vessel__id', 'vessel__name'
        ).annotate(
            transaction_count=Count('id'),
            total_quantity=Sum('quantity'),
            total_amount=Sum(F('quantity') * F('unit_price'))
        ).order_by('-transaction_count')
        
        # Get daily activity
        daily_activity = transactions.values('transaction_date').annotate(
            transaction_count=Count('id'),
            total_amount=Sum(F('quantity') * F('unit_price'))
        ).order_by('transaction_date')
        
        # Calculate totals
        total_transactions = transactions.count()
        total_amount = transactions.aggregate(
            total=Sum(F('quantity') * F('unit_price'))
        )['total'] or 0
        
        return Response({
            'user_id': user.id,
            'username': user.username,
            'date_range': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'days': days
            },
            'summary': {
                'total_transactions': total_transactions,
                'total_transaction_amount': float(total_amount),
                'average_transaction_amount': (
                    float(total_amount) / total_transactions if total_transactions > 0 else 0
                ),
                'active_days': daily_activity.count()
            },
            'activity_by_type': list(activity_by_type),
            'activity_by_vessel': list(activity_by_vessel),
            'daily_activity': list(daily_activity)
        })
    
    @action(detail=True, methods=['post'])
    def assign_vessels(self, request, pk=None):
        """
        Assign vessels to a user.
        
        This will be fully implemented when UserVesselAssignment model is created.
        For now, returns a placeholder response.
        """
        user = self.get_object()
        vessel_ids = request.data.get('vessel_ids', [])
        
        # Validate vessel IDs
        if not isinstance(vessel_ids, list):
            return Response({
                'error': 'vessel_ids must be a list of vessel IDs.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            vessel_ids = [int(vid) for vid in vessel_ids]
        except (ValueError, TypeError):
            return Response({
                'error': 'All vessel_ids must be valid integers.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate vessels exist
        from vessels.models import Vessel
        vessels = Vessel.objects.filter(id__in=vessel_ids, active=True)
        
        if vessels.count() != len(vessel_ids):
            return Response({
                'error': 'One or more vessel IDs are invalid or inactive.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # TODO: Implement UserVesselAssignment creation
        # For now, return success message
        return Response({
            'message': f'Successfully assigned {vessels.count()} vessels to user {user.username}.',
            'user_id': user.id,
            'assigned_vessels': [
                {'id': v.id, 'name': v.name} for v in vessels
            ]
        })
    
    @action(detail=True, methods=['get'])
    def assigned_vessels(self, request, pk=None):
        """
        Get vessels assigned to a user.
        
        This will be fully implemented when UserVesselAssignment model is created.
        """
        user = self.get_object()
        
        # TODO: Implement actual vessel assignment retrieval
        # For now, return all vessels if superuser, empty list otherwise
        if user.is_superuser:
            from vessels.models import Vessel
            vessels = Vessel.objects.filter(active=True).values('id', 'name', 'name_ar', 'has_duty_free')
            return Response({
                'user_id': user.id,
                'username': user.username,
                'is_superuser': True,
                'assigned_vessels': list(vessels),
                'assignment_type': 'all_vessels_superuser'
            })
        else:
            return Response({
                'user_id': user.id,
                'username': user.username,
                'is_superuser': False,
                'assigned_vessels': [],
                'assignment_type': 'specific_vessels',
                'note': 'User vessel assignments not yet implemented'
            })
    
    @action(detail=False, methods=['get'])
    def statistics(self, request):
        """
        Get overall user statistics.
        
        Returns system-wide user statistics and insights.
        """
        # Basic counts
        total_users = self.get_queryset().count()
        active_users = self.get_queryset().filter(is_active=True).count()
        staff_users = self.get_queryset().filter(is_staff=True).count()
        superusers = self.get_queryset().filter(is_superuser=True).count()
        
        # Activity statistics
        from datetime import datetime, timedelta
        week_ago = datetime.now().date() - timedelta(days=7)
        
        users_with_activity = self.get_queryset().annotate(
            transaction_count=Count('transaction'),
            recent_transaction_count=Count(
                'transaction',
                filter=Q(transaction__transaction_date__gte=week_ago)
            )
        )
        
        active_this_week = users_with_activity.filter(recent_transaction_count__gt=0).count()
        
        # Group statistics
        group_stats = Group.objects.annotate(
            user_count=Count('user')
        ).values('name', 'user_count').order_by('-user_count')
        
        return Response({
            'user_counts': {
                'total_users': total_users,
                'active_users': active_users,
                'inactive_users': total_users - active_users,
                'staff_users': staff_users,
                'superusers': superusers,
                'regular_users': total_users - staff_users
            },
            'activity_stats': {
                'users_with_transactions': users_with_activity.filter(transaction_count__gt=0).count(),
                'users_active_this_week': active_this_week,
                'users_never_active': users_with_activity.filter(transaction_count=0).count()
            },
            'group_distribution': list(group_stats)
        })
    
    def perform_create(self, serializer):
        """Handle user creation with additional setup."""
        user = serializer.save()
        
        # Add any additional user setup here
        # For example, default group assignment, welcome email, etc.
        
        return user
    
    def perform_update(self, serializer):
        """Handle user updates with permission checks."""
        # Prevent non-superusers from modifying superuser status
        if not self.request.user.is_superuser:
            if 'is_superuser' in serializer.validated_data:
                serializer.validated_data.pop('is_superuser')
            if 'is_staff' in serializer.validated_data:
                serializer.validated_data.pop('is_staff')
        
        return serializer.save()
    
    def destroy(self, request, *args, **kwargs):
        """
        Override destroy to prevent deletion of users with transaction history.
        
        Instead of deleting, mark user as inactive if they have transactions.
        """
        user = self.get_object()
        
        # Prevent self-deletion
        if user == request.user:
            return Response({
                'error': 'You cannot delete your own account.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if user has any transactions
        if user.transactions.exists():
            # Instead of deleting, mark as inactive
            user.is_active = False
            user.save()
            
            return Response({
                'message': 'User has transaction history and has been marked as inactive instead of deleted.',
                'user_id': user.id,
                'username': user.username,
                'status': 'inactive'
            }, status=status.HTTP_200_OK)
        else:
            # Safe to delete if no transactions
            return super().destroy(request, *args, **kwargs)