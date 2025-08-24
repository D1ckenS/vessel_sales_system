"""
Vessel Management Utilities
Provides helper functions for vessel assignment management and access control.
"""

from django.contrib.auth.models import User
from django.db.models import Q
from vessels.models import Vessel
from .models import UserVesselAssignment


class VesselAccessHelper:
    """Helper class for vessel access control and management"""
    
    @staticmethod
    def get_user_vessels(user, include_inactive=False):
        """
        Get all vessels a user has access to.
        
        Args:
            user: User instance
            include_inactive: Whether to include inactive vessel assignments
            
        Returns:
            QuerySet of Vessel objects the user can access
        """
        if user.is_superuser:
            # SuperUsers have access to all active vessels
            return Vessel.objects.filter(active=True)
        
        # Get vessels through assignments
        assignment_filter = Q(user=user)
        if not include_inactive:
            assignment_filter &= Q(is_active=True)
        
        vessel_ids = UserVesselAssignment.objects.filter(
            assignment_filter
        ).values_list('vessel_id', flat=True)
        
        return Vessel.objects.filter(id__in=vessel_ids, active=True)
    
    @staticmethod
    def get_user_vessel_ids(user):
        """
        Get vessel IDs that user has access to (optimized version with caching).
        
        Args:
            user: User instance
            
        Returns:
            List of vessel IDs the user can access
        """
        from frontend.utils.cache_helpers import VesselCacheHelper
        
        # Try to get from cache first
        cached_vessel_ids = VesselCacheHelper.get_cached_user_vessel_ids(user.id)
        if cached_vessel_ids is not None:
            return cached_vessel_ids
        
        # Not in cache, fetch from database
        if user.is_superuser:
            vessel_ids = list(Vessel.objects.filter(active=True).values_list('id', flat=True))
        else:
            vessel_ids = list(UserVesselAssignment.objects.filter(
                user=user, is_active=True
            ).values_list('vessel_id', flat=True))
        
        # Cache the result for 1 hour
        VesselCacheHelper.cache_user_vessel_ids(user.id, vessel_ids, timeout=3600)
        
        return vessel_ids
    
    @staticmethod
    def can_user_access_vessel(user, vessel):
        """
        Check if a user can access a specific vessel.
        
        Args:
            user: User instance
            vessel: Vessel instance or vessel ID
            
        Returns:
            bool: True if user can access the vessel
        """
        if user.is_superuser:
            return True
        
        vessel_id = vessel.id if hasattr(vessel, 'id') else vessel
        
        return UserVesselAssignment.objects.filter(
            user=user,
            vessel_id=vessel_id,
            is_active=True
        ).exists()
    
    @staticmethod
    def get_user_vessel_permissions(user, vessel):
        """
        Get specific permissions a user has for a vessel.
        
        Args:
            user: User instance
            vessel: Vessel instance or vessel ID
            
        Returns:
            dict: Permission dictionary or None if no access
        """
        if user.is_superuser:
            return {
                'can_make_sales': True,
                'can_receive_inventory': True,
                'can_initiate_transfers': True,
                'can_approve_transfers': True,
                'is_superuser_access': True
            }
        
        vessel_id = vessel.id if hasattr(vessel, 'id') else vessel
        
        try:
            assignment = UserVesselAssignment.objects.get(
                user=user,
                vessel_id=vessel_id,
                is_active=True
            )
            return {
                'can_make_sales': assignment.can_make_sales,
                'can_receive_inventory': assignment.can_receive_inventory,
                'can_initiate_transfers': assignment.can_initiate_transfers,
                'can_approve_transfers': assignment.can_approve_transfers,
                'is_superuser_access': False
            }
        except UserVesselAssignment.DoesNotExist:
            return None
    
    @staticmethod
    def get_users_without_vessel_assignments():
        """
        Get all users who don't have any vessel assignments.
        
        Returns:
            QuerySet of User objects without vessel assignments
        """
        assigned_user_ids = UserVesselAssignment.objects.values_list('user_id', flat=True).distinct()
        return User.objects.exclude(id__in=assigned_user_ids).exclude(is_superuser=True)
    
    @staticmethod
    def assign_user_to_vessel(user, vessel, assigned_by=None, **permissions):
        """
        Assign a user to a vessel with specific permissions.
        
        Args:
            user: User instance
            vessel: Vessel instance
            assigned_by: User who made the assignment (optional)
            **permissions: Permission flags (can_make_sales, etc.)
            
        Returns:
            UserVesselAssignment instance
        """
        defaults = {
            'is_active': True,
            'can_make_sales': permissions.get('can_make_sales', True),
            'can_receive_inventory': permissions.get('can_receive_inventory', True),
            'can_initiate_transfers': permissions.get('can_initiate_transfers', True),
            'can_approve_transfers': permissions.get('can_approve_transfers', True),
            'assigned_by': assigned_by,
            'notes': permissions.get('notes', f'Assigned to {vessel.name}')
        }
        
        assignment, created = UserVesselAssignment.objects.get_or_create(
            user=user,
            vessel=vessel,
            defaults=defaults
        )
        
        if not created and assignment.is_active:
            # Update existing assignment
            for key, value in defaults.items():
                if key != 'notes':  # Don't overwrite notes
                    setattr(assignment, key, value)
            assignment.save()
        
        return assignment
    
    @staticmethod
    def filter_vessels_by_user_access(vessels_queryset, user):
        """
        Filter a vessels queryset to only include vessels the user can access.
        
        Args:
            vessels_queryset: QuerySet of Vessel objects
            user: User instance
            
        Returns:
            Filtered QuerySet of Vessel objects
        """
        if user.is_superuser:
            return vessels_queryset.filter(active=True)
        
        accessible_vessel_ids = UserVesselAssignment.objects.filter(
            user=user,
            is_active=True
        ).values_list('vessel_id', flat=True)
        
        return vessels_queryset.filter(
            id__in=accessible_vessel_ids,
            active=True
        )


class VesselOperationValidator:
    """Validator for vessel-based operations"""
    
    @staticmethod
    def validate_sales_access(user, vessel):
        """Validate user can make sales on vessel"""
        if user.is_superuser:
            return True, None
            
        permissions = VesselAccessHelper.get_user_vessel_permissions(user, vessel)
        if not permissions:
            return False, f"User {user.username} does not have access to vessel {vessel.name}"
        
        if not permissions['can_make_sales']:
            return False, f"User {user.username} does not have sales permission for vessel {vessel.name}"
        
        return True, None
    
    @staticmethod
    def validate_inventory_access(user, vessel):
        """Validate user can receive inventory on vessel"""
        if user.is_superuser:
            return True, None
            
        permissions = VesselAccessHelper.get_user_vessel_permissions(user, vessel)
        if not permissions:
            return False, f"User {user.username} does not have access to vessel {vessel.name}"
        
        if not permissions['can_receive_inventory']:
            return False, f"User {user.username} does not have inventory permission for vessel {vessel.name}"
        
        return True, None
    
    @staticmethod
    def validate_transfer_initiation(user, from_vessel):
        """Validate user can initiate transfers from vessel"""
        if user.is_superuser:
            return True, None
            
        permissions = VesselAccessHelper.get_user_vessel_permissions(user, from_vessel)
        if not permissions:
            return False, f"User {user.username} does not have access to vessel {from_vessel.name}"
        
        if not permissions['can_initiate_transfers']:
            return False, f"User {user.username} does not have transfer initiation permission for vessel {from_vessel.name}"
        
        return True, None
    
    @staticmethod
    def validate_transfer_approval(user, to_vessel):
        """Validate user can approve transfers to vessel"""
        if user.is_superuser:
            return True, None
            
        permissions = VesselAccessHelper.get_user_vessel_permissions(user, to_vessel)
        if not permissions:
            return False, f"User {user.username} does not have access to vessel {to_vessel.name}"
        
        if not permissions['can_approve_transfers']:
            return False, f"User {user.username} does not have transfer approval permission for vessel {to_vessel.name}"
        
        return True, None


class VesselFormHelper:
    """Helper class for vessel form auto-population and context-aware selection"""
    
    @staticmethod
    def get_user_default_vessel(user):
        """
        Get the default vessel for a user to auto-populate forms.
        
        Args:
            user: User instance
            
        Returns:
            Vessel instance or None
        """
        if user.is_superuser:
            # SuperUsers get the first active vessel as default
            from vessels.models import Vessel
            return Vessel.objects.filter(active=True).first()
        
        # Get user's first assigned vessel
        assignment = UserVesselAssignment.objects.filter(
            user=user,
            is_active=True
        ).select_related('vessel').first()
        
        return assignment.vessel if assignment else None
    
    @staticmethod
    def should_vessel_dropdown_be_readonly(user):
        """
        Determine if vessel dropdown should be read-only for a user.
        
        Args:
            user: User instance
            
        Returns:
            bool: True if dropdown should be read-only (user has exactly 1 vessel)
        """
        if user.is_superuser:
            return False  # SuperUsers always get dropdown
        
        # Count user's active vessel assignments
        assignment_count = UserVesselAssignment.objects.filter(
            user=user,
            is_active=True
        ).count()
        
        return assignment_count == 1
    
    @staticmethod
    def get_user_vessel_choices(user):
        """
        Get vessel choices for dropdowns with smart ordering.
        
        Args:
            user: User instance
            
        Returns:
            List of (vessel_id, vessel_name, is_default) tuples
        """
        if user.is_superuser:
            from vessels.models import Vessel
            vessels = Vessel.objects.filter(active=True).order_by('name')
            default_vessel = vessels.first()
            return [
                (v.id, v.name, v.id == (default_vessel.id if default_vessel else None))
                for v in vessels
            ]
        
        assignments = UserVesselAssignment.objects.filter(
            user=user,
            is_active=True
        ).select_related('vessel').order_by('assigned_date')
        
        if not assignments.exists():
            return []
        
        # First assigned vessel is default
        first_assignment = assignments.first()
        return [
            (a.vessel.id, a.vessel.name, a.vessel.id == first_assignment.vessel.id)
            for a in assignments
        ]
    
    @staticmethod
    def get_context_aware_vessels(user, operation_type='general'):
        """
        Get vessels with context-aware filtering based on operation type.
        
        Args:
            user: User instance
            operation_type: 'sales', 'supply', 'transfer_from', 'transfer_to', or 'general'
            
        Returns:
            QuerySet of Vessel objects with appropriate filtering
        """
        user_vessels = VesselAccessHelper.get_user_vessels(user)
        
        if operation_type == 'sales':
            # For sales, filter vessels where user can make sales
            if user.is_superuser:
                return user_vessels
            
            vessel_ids = UserVesselAssignment.objects.filter(
                user=user,
                is_active=True,
                can_make_sales=True
            ).values_list('vessel_id', flat=True)
            
            return user_vessels.filter(id__in=vessel_ids)
        
        elif operation_type == 'supply':
            # For supply, filter vessels where user can receive inventory
            if user.is_superuser:
                return user_vessels
            
            vessel_ids = UserVesselAssignment.objects.filter(
                user=user,
                is_active=True,
                can_receive_inventory=True
            ).values_list('vessel_id', flat=True)
            
            return user_vessels.filter(id__in=vessel_ids)
        
        elif operation_type == 'transfer_from':
            # For transfer source, filter vessels where user can initiate transfers
            if user.is_superuser:
                return user_vessels
            
            vessel_ids = UserVesselAssignment.objects.filter(
                user=user,
                is_active=True,
                can_initiate_transfers=True
            ).values_list('vessel_id', flat=True)
            
            return user_vessels.filter(id__in=vessel_ids)
        
        elif operation_type == 'transfer_to':
            # For transfer destination, filter vessels where user can approve transfers
            if user.is_superuser:
                return user_vessels
            
            vessel_ids = UserVesselAssignment.objects.filter(
                user=user,
                is_active=True,
                can_approve_transfers=True
            ).values_list('vessel_id', flat=True)
            
            return user_vessels.filter(id__in=vessel_ids)
        
        else:
            # General access - all assigned vessels
            return user_vessels
    
    @staticmethod
    def add_vessel_context_to_view(context, user, operation_type='general'):
        """
        Add vessel-related context data to view context.
        
        Args:
            context: View context dictionary
            user: User instance
            operation_type: Operation type for context-aware filtering
            
        Returns:
            Updated context dictionary
        """
        default_vessel = VesselFormHelper.get_user_default_vessel(user)
        vessel_choices = VesselFormHelper.get_user_vessel_choices(user)
        context_vessels = VesselFormHelper.get_context_aware_vessels(user, operation_type)
        
        context.update({
            'user_default_vessel': default_vessel,
            'user_vessel_choices': vessel_choices,
            'context_aware_vessels': context_vessels,
            'vessel_auto_populate_enabled': True,
            'vessel_dropdown_readonly': VesselFormHelper.should_vessel_dropdown_be_readonly(user),
        })
        
        return context