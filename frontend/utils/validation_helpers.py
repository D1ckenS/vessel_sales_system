"""
Validation helpers to eliminate duplicate validation patterns.
Eliminates 6+ instances of repeated validation logic.
"""

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from .response_helpers import JsonResponseHelper


class ValidationHelper:
    """
    Helper for common validation patterns.
    
    Eliminates duplicate validation logic found in:
    - auth_views.py (6+ functions)
    """
    
    @staticmethod
    def validate_required_fields(data, required_fields):
        """
        Validate that all required fields are present and non-empty.
        
        Args:
            data (dict): Data to validate
            required_fields (list): List of required field names
            
        Returns:
            tuple: (is_valid, error_response) - error_response is None if valid
            
        Usage:
            valid, error = ValidationHelper.validate_required_fields(
                data, ['username', 'password']
            )
            if not valid:
                return error
        """
        for field in required_fields:
            value = data.get(field, '').strip() if isinstance(data.get(field), str) else data.get(field)
            if not value:
                field_name = field.replace('_', ' ').title()
                return False, JsonResponseHelper.error(f'{field_name} is required')
        
        return True, None
    
    @staticmethod
    def validate_unique_name(model_class, name, exclude_id=None, field_name='name'):
        """
        Validate that a name is unique for a model.
        
        Args:
            model_class: Django model class
            name (str): Name to validate
            exclude_id (int, optional): ID to exclude from uniqueness check
            field_name (str): Field name to check (default: 'name')
            
        Returns:
            tuple: (is_valid, error_response) - error_response is None if valid
            
        Usage:
            valid, error = ValidationHelper.validate_unique_name(
                User, username, exclude_id=user.id, field_name='username'
            )
            if not valid:
                return error
        """
        query_kwargs = {field_name: name}
        queryset = model_class.objects.filter(**query_kwargs)
        
        if exclude_id:
            queryset = queryset.exclude(id=exclude_id)
        
        if queryset.exists():
            model_name = model_class.__name__
            return False, JsonResponseHelper.error(
                f'{model_name} with {field_name} "{name}" already exists'
            )
        
        return True, None
    
    @staticmethod
    def validate_username(username, exclude_user_id=None):
        """
        Validate username requirements.
        
        Args:
            username (str): Username to validate
            exclude_user_id (int, optional): User ID to exclude from uniqueness check
            
        Returns:
            tuple: (is_valid, error_response) - error_response is None if valid
            
        Usage:
            valid, error = ValidationHelper.validate_username(username, user.id)
            if not valid:
                return error
        """
        if not username or not username.strip():
            return False, JsonResponseHelper.error('Username is required')
        
        username = username.strip()
        
        # Check uniqueness
        return ValidationHelper.validate_unique_name(
            User, username, exclude_user_id, 'username'
        )
    
    @staticmethod
    def validate_password_strength(password, confirm_password=None):
        """
        Validate password strength and confirmation.
        
        Args:
            password (str): Password to validate
            confirm_password (str, optional): Password confirmation
            
        Returns:
            tuple: (is_valid, error_response) - error_response is None if valid
            
        Usage:
            valid, error = ValidationHelper.validate_password_strength(
                password, confirm_password
            )
            if not valid:
                return error
        """
        if not password:
            return False, JsonResponseHelper.error('Password is required')
        
        # Check password confirmation
        if confirm_password is not None and password != confirm_password:
            return False, JsonResponseHelper.error('Passwords do not match')
        
        # Validate password strength using Django validators
        try:
            validate_password(password)
            return True, None
        except ValidationError as e:
            error_msg = '; '.join(e.messages)
            return False, JsonResponseHelper.error(f'Password validation failed: {error_msg}')
    
    @staticmethod
    def validate_email(email, exclude_user_id=None):
        """
        Validate email format and uniqueness.
        
        Args:
            email (str): Email to validate
            exclude_user_id (int, optional): User ID to exclude from uniqueness check
            
        Returns:
            tuple: (is_valid, error_response) - error_response is None if valid
            
        Usage:
            valid, error = ValidationHelper.validate_email(email, user.id)
            if not valid:
                return error
        """
        if not email:
            return True, None  # Email is optional in most cases
        
        email = email.strip()
        
        # Basic email format validation (Django's EmailField will do more)
        if '@' not in email or '.' not in email.split('@')[-1]:
            return False, JsonResponseHelper.error('Invalid email format')
        
        # Check uniqueness
        return ValidationHelper.validate_unique_name(
            User, email, exclude_user_id, 'email'
        )
    
    @staticmethod
    def validate_vessel_data(data, exclude_vessel_id=None):
        """
        Validate vessel creation/update data.
        
        Args:
            data (dict): Vessel data to validate
            exclude_vessel_id (int, optional): Vessel ID to exclude from uniqueness check
            
        Returns:
            tuple: (is_valid, error_response) - error_response is None if valid
            
        Usage:
            valid, error = ValidationHelper.validate_vessel_data(data, vessel.id)
            if not valid:
                return error
        """
        from vessels.models import Vessel
        
        # Validate required fields
        valid, error = ValidationHelper.validate_required_fields(data, ['name'])
        if not valid:
            return valid, error
        
        name = data['name'].strip()
        
        # Validate unique name
        return ValidationHelper.validate_unique_name(
            Vessel, name, exclude_vessel_id, 'name'
        )
    
    @staticmethod
    def validate_group_data(data, exclude_group_id=None):
        """
        Validate group creation/update data.
        
        Args:
            data (dict): Group data to validate
            exclude_group_id (int, optional): Group ID to exclude from uniqueness check
            
        Returns:
            tuple: (is_valid, error_response) - error_response is None if valid
            
        Usage:
            valid, error = ValidationHelper.validate_group_data(data, group.id)
            if not valid:
                return error
        """
        from django.contrib.auth.models import Group
        
        # Validate required fields
        valid, error = ValidationHelper.validate_required_fields(data, ['name'])
        if not valid:
            return valid, error
        
        name = data['name'].strip()
        
        # Validate unique name
        return ValidationHelper.validate_unique_name(
            Group, name, exclude_group_id, 'name'
        )