"""
User API Serializers
Handles user data serialization with vessel assignments and permissions.
"""

from rest_framework import serializers
from django.contrib.auth.models import User, Group
from django.contrib.auth.password_validation import validate_password


class GroupSerializer(serializers.ModelSerializer):
    """Group serializer for user permissions."""
    
    class Meta:
        model = Group
        fields = ['id', 'name']


class UserSerializer(serializers.ModelSerializer):
    """Basic user serializer."""
    
    # Group information
    groups = GroupSerializer(many=True, read_only=True)
    group_names = serializers.SerializerMethodField()
    
    # User activity
    last_login_formatted = serializers.SerializerMethodField()
    is_active_display = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'is_active', 'is_staff', 'is_superuser', 'last_login',
            'last_login_formatted', 'is_active_display', 'date_joined',
            'groups', 'group_names'
        ]
        read_only_fields = ['id', 'date_joined', 'last_login']
    
    def get_group_names(self, obj):
        """Get list of group names for the user."""
        return [group.name for group in obj.groups.all()]
    
    def get_last_login_formatted(self, obj):
        """Get formatted last login time."""
        if obj.last_login:
            return obj.last_login.strftime('%Y-%m-%d %H:%M:%S')
        return 'Never'
    
    def get_is_active_display(self, obj):
        """Get human-readable active status."""
        return 'Active' if obj.is_active else 'Inactive'


class UserDetailSerializer(UserSerializer):
    """Detailed user serializer with vessel assignments and activity."""
    
    # Vessel assignments (if UserVesselAssignment model exists)
    assigned_vessels = serializers.SerializerMethodField()
    recent_activity = serializers.SerializerMethodField()
    permission_summary = serializers.SerializerMethodField()
    
    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + [
            'assigned_vessels', 'recent_activity', 'permission_summary'
        ]
    
    def get_assigned_vessels(self, obj):
        """Get vessels assigned to this user."""
        # This will be implemented when UserVesselAssignment model is created
        # For now, return all vessels if superuser, empty list otherwise
        if obj.is_superuser:
            from vessels.models import Vessel
            return [{'id': v.id, 'name': v.name} for v in Vessel.objects.filter(active=True)]
        return []
    
    def get_recent_activity(self, obj):
        """Get recent transaction activity for this user."""
        from datetime import datetime, timedelta
        from django.db.models import Count, Sum, F
        
        week_ago = datetime.now().date() - timedelta(days=7)
        
        # Get transaction counts by type
        activity = obj.transaction.filter(
            transaction_date__gte=week_ago
        ).values('transaction_type').annotate(
            count=Count('id'),
            total_amount=Sum(F('quantity') * F('unit_price'))
        )
        
        return {item['transaction_type']: item for item in activity}
    
    def get_permission_summary(self, obj):
        """Get user permission summary."""
        return {
            'can_manage_users': obj.is_superuser or obj.groups.filter(name='Admin').exists(),
            'can_manage_vessels': obj.is_superuser or obj.groups.filter(name__in=['Admin', 'Manager']).exists(),
            'can_view_reports': obj.is_superuser or obj.groups.filter(name__in=['Admin', 'Manager', 'Reports']).exists(),
            'can_process_sales': obj.is_superuser or obj.groups.filter(name__in=['Admin', 'Manager', 'Operations', 'Sales']).exists(),
            'can_manage_inventory': obj.is_superuser or obj.groups.filter(name__in=['Admin', 'Manager', 'Operations']).exists(),
        }


class UserCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating new users."""
    
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    group_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        help_text="List of group IDs to assign to the user"
    )
    
    class Meta:
        model = User
        fields = [
            'username', 'email', 'first_name', 'last_name',
            'password', 'password_confirm', 'is_active', 'group_ids'
        ]
    
    def validate_username(self, value):
        """Validate username is unique and follows rules."""
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        
        if len(value) < 3:
            raise serializers.ValidationError("Username must be at least 3 characters long.")
        
        return value
    
    def validate_email(self, value):
        """Validate email is unique if provided."""
        if value and User.objects.filter(email=value).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return value
    
    def validate(self, data):
        """Validate password confirmation matches."""
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({
                'password_confirm': 'Password confirmation does not match.'
            })
        return data
    
    def create(self, validated_data):
        """Create user with password hashing and group assignment."""
        # Remove password_confirm and group_ids from validated_data
        validated_data.pop('password_confirm')
        group_ids = validated_data.pop('group_ids', [])
        
        # Create user
        user = User.objects.create_user(**validated_data)
        
        # Assign groups
        if group_ids:
            groups = Group.objects.filter(id__in=group_ids)
            user.groups.set(groups)
        
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating users."""
    
    group_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        help_text="List of group IDs to assign to the user"
    )
    
    class Meta:
        model = User
        fields = [
            'email', 'first_name', 'last_name', 'is_active', 'group_ids'
        ]
    
    def validate_email(self, value):
        """Validate email is unique if provided (excluding current user)."""
        if value:
            queryset = User.objects.filter(email=value)
            if self.instance:
                queryset = queryset.exclude(pk=self.instance.pk)
            
            if queryset.exists():
                raise serializers.ValidationError("A user with this email already exists.")
        return value
    
    def update(self, instance, validated_data):
        """Update user with group assignment."""
        group_ids = validated_data.pop('group_ids', None)
        
        # Update user fields
        user = super().update(instance, validated_data)
        
        # Update groups if provided
        if group_ids is not None:
            groups = Group.objects.filter(id__in=group_ids)
            user.groups.set(groups)
        
        return user


class UserPasswordChangeSerializer(serializers.Serializer):
    """Serializer for changing user password."""
    
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(write_only=True)
    
    def validate_old_password(self, value):
        """Validate old password is correct."""
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Old password is incorrect.")
        return value
    
    def validate(self, data):
        """Validate new password confirmation matches."""
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError({
                'new_password_confirm': 'New password confirmation does not match.'
            })
        return data
    
    def save(self):
        """Change user password."""
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()
        return user


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer for user profile information."""
    
    full_name = serializers.SerializerMethodField()
    group_names = serializers.SerializerMethodField()
    assigned_vessels = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'full_name',
            'is_staff', 'is_superuser', 'last_login', 'date_joined',
            'group_names', 'assigned_vessels'
        ]
        read_only_fields = fields  # All fields are read-only for profile view
    
    def get_full_name(self, obj):
        """Get user's full name."""
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username
    
    def get_group_names(self, obj):
        """Get list of group names for the user."""
        return [group.name for group in obj.groups.all()]
    
    def get_assigned_vessels(self, obj):
        """Get vessels assigned to this user."""
        # This will be implemented when UserVesselAssignment model is created
        # For now, return all vessels if superuser, empty list otherwise
        if obj.is_superuser:
            from vessels.models import Vessel
            return [
                {'id': v.id, 'name': v.name, 'name_ar': v.name_ar, 'has_duty_free': v.has_duty_free}
                for v in Vessel.objects.filter(active=True)
            ]
        return []


class UserSummarySerializer(serializers.ModelSerializer):
    """Minimal user serializer for references and dropdowns."""
    
    full_name = serializers.SerializerMethodField()
    
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'full_name', 'is_active']
    
    def get_full_name(self, obj):
        """Get user's full name."""
        return f"{obj.first_name} {obj.last_name}".strip() or obj.username