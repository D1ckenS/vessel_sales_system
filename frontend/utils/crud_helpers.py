"""
CRUD operation helpers to eliminate duplicate CRUD patterns.
Eliminates 8+ instances of repeated CRUD logic.
"""

import json
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from .response_helpers import JsonResponseHelper


class CRUDHelper:
    """
    Helper for common CRUD operations with standardized responses.
    
    Eliminates duplicate CRUD patterns found in:
    - auth_views.py (8+ functions)
    """
    
    @staticmethod
    def safe_get_object(model_class, object_id, object_name=None):
        """
        Safely get object with standardized error handling.
        
        Args:
            model_class: Django model class
            object_id: ID of object to retrieve
            object_name (str, optional): Name for error messages
            
        Returns:
            tuple: (object, error_response) - error_response is None if successful
            
        Usage:
            user, error = CRUDHelper.safe_get_object(User, user_id, 'User')
            if error:
                return error
        """
        if not object_name:
            object_name = model_class.__name__
            
        try:
            obj = get_object_or_404(model_class, id=object_id)
            return obj, None
        except Exception:
            return None, JsonResponseHelper.not_found(object_name)
    
    @staticmethod
    def safe_json_load(request):
        """
        Safely load JSON from request body.
        
        Args:
            request: Django request object
            
        Returns:
            tuple: (data, error_response) - error_response is None if successful
            
        Usage:
            data, error = CRUDHelper.safe_json_load(request)
            if error:
                return error
        """
        try:
            data = json.loads(request.body)
            return data, None
        except (json.JSONDecodeError, ValueError):
            return None, JsonResponseHelper.error('Invalid JSON data')
    
    @staticmethod
    def safe_update_object(obj, data, allowed_fields, required_fields=None):
        """
        Safely update object with validation.
        
        Args:
            obj: Django model instance
            data (dict): Update data
            allowed_fields (list): List of allowed field names
            required_fields (list, optional): List of required field names
            
        Returns:
            tuple: (success, error_response) - error_response is None if successful
            
        Usage:
            success, error = CRUDHelper.safe_update_object(
                user, data, ['username', 'email'], ['username']
            )
            if not success:
                return error
        """
        if required_fields:
            for field in required_fields:
                if not data.get(field):
                    return False, JsonResponseHelper.error(f'{field} is required')
        
        try:
            # Update only allowed fields
            for field in allowed_fields:
                if field in data:
                    setattr(obj, field, data[field])
            
            obj.full_clean()  # Validate model
            obj.save()
            return True, None
            
        except ValidationError as e:
            error_msg = '; '.join(e.messages) if hasattr(e, 'messages') else str(e)
            return False, JsonResponseHelper.error(f'Validation error: {error_msg}')
        except Exception as e:
            return False, JsonResponseHelper.error(str(e))
    
    @staticmethod
    def toggle_boolean_field(obj, field_name, object_name=None):
        """
        Toggle a boolean field and return standardized response.
        
        Args:
            obj: Django model instance
            field_name (str): Name of boolean field to toggle
            object_name (str, optional): Name for response messages
            
        Returns:
            JsonResponse: Standardized toggle response
            
        Usage:
            return CRUDHelper.toggle_boolean_field(user, 'is_active', 'User')
        """
        if not object_name:
            object_name = obj.__class__.__name__
        
        try:
            # Get current value and toggle it
            current_value = getattr(obj, field_name)
            new_value = not current_value
            setattr(obj, field_name, new_value)
            obj.save()
            
            # Determine status text based on field name
            if field_name == 'is_active':
                status = 'activated' if new_value else 'deactivated'
            elif field_name == 'is_completed':
                status = 'completed' if new_value else 'in progress'
            else:
                status = 'enabled' if new_value else 'disabled'
            
            # Get object identifier (try common fields)
            identifier = getattr(obj, 'username', None) or \
                        getattr(obj, 'name', None) or \
                        getattr(obj, 'trip_number', None) or \
                        getattr(obj, 'po_number', None) or \
                        str(obj)
            
            return JsonResponseHelper.success(
                message=f'{object_name} "{identifier}" {status} successfully',
                new_status=new_value
            )
            
        except Exception as e:
            return JsonResponseHelper.error(str(e))
    
    @staticmethod
    def safe_delete_with_confirmation(obj, related_objects=None, force_header='X-Force-Delete'):
        """
        Delete object with confirmation if it has related objects.
        
        Args:
            obj: Django model instance to delete
            related_objects (dict, optional): Dict of related object info
            force_header (str): Header name for force delete confirmation
            
        Returns:
            tuple: (deleted, response) - response is confirmation or success
            
        Usage:
            related = {'transaction_count': obj.transactions.count()}
            deleted, response = CRUDHelper.safe_delete_with_confirmation(
                trip, related, request
            )
            if not deleted:
                return response  # Either confirmation or error
        """
        object_name = obj.__class__.__name__
        
        try:
            # Check for related objects
            if related_objects:
                total_related = sum(related_objects.values())
                if total_related > 0:
                    # Build confirmation message
                    related_info = []
                    for key, count in related_objects.items():
                        if count > 0:
                            related_info.append(f'{count} {key.replace("_", " ")}')
                    
                    message = f'This {object_name.lower()} has {", ".join(related_info)}. Delete anyway?'
                    
                    return False, JsonResponseHelper.requires_confirmation(
                        message=message,
                        confirmation_data=related_objects
                    )
            
            # Get identifier before deletion
            identifier = getattr(obj, 'username', None) or \
                        getattr(obj, 'name', None) or \
                        getattr(obj, 'trip_number', None) or \
                        getattr(obj, 'po_number', None) or \
                        str(obj)
            
            # Delete object
            obj.delete()
            
            return True, JsonResponseHelper.success(
                message=f'{object_name} "{identifier}" deleted successfully'
            )
            
        except Exception as e:
            return False, JsonResponseHelper.error(str(e))


class AdminActionHelper:
    """
    Helper for admin-specific actions like self-protection.
    """
    
    @staticmethod
    def prevent_self_action(request, target_user_id, action_name='perform this action'):
        """
        Prevent user from performing action on themselves.
        
        Args:
            request: Django request object
            target_user_id (int): ID of target user
            action_name (str): Name of action for error message
            
        Returns:
            JsonResponse or None: Error response if self-action, None if allowed
            
        Usage:
            self_error = AdminActionHelper.prevent_self_action(
                request, user_id, 'deactivate'
            )
            if self_error:
                return self_error
        """
        if int(target_user_id) == request.user.id:
            return JsonResponseHelper.error(
                f'You cannot {action_name} on yourself'
            )
        return None
    
    @staticmethod
    def check_force_delete(request, header_name='X-Force-Delete'):
        """
        Check if force delete header is present.
        
        Args:
            request: Django request object
            header_name (str): Name of force delete header
            
        Returns:
            bool: True if force delete requested
            
        Usage:
            force_delete = AdminActionHelper.check_force_delete(request)
        """
        return request.headers.get(header_name) == 'true'