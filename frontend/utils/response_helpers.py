"""
JSON Response helpers to eliminate duplicate response patterns.
Eliminates 15+ instances of repeated JsonResponse code.
"""

from django.http import JsonResponse
from django.contrib import messages
from django.shortcuts import redirect


class JsonResponseHelper:
    """
    Standardized JSON response helper for AJAX endpoints.
    
    Eliminates repeated JsonResponse patterns found in:
    - auth_views.py (15+ functions)
    """
    
    @staticmethod
    def success(message=None, data=None, **extra_data):
        """
        Return standardized success response.
        
        Args:
            message (str, optional): Success message
            data (dict, optional): Response data
            **extra_data: Additional fields to include
            
        Returns:
            JsonResponse: Standardized success response
            
        Usage:
            return JsonResponseHelper.success(
                message='User created successfully',
                data={'user_id': user.id}
            )
        """
        response = {'success': True}
        
        if message:
            response['message'] = message
            
        if data:
            response.update(data)
            
        if extra_data:
            response.update(extra_data)
            
        return JsonResponse(response)
    
    @staticmethod
    def error(error_message, status=400, **extra_data):
        """
        Return standardized error response.
        
        Args:
            error_message (str): Error message
            status (int): HTTP status code (default: 400)
            **extra_data: Additional fields to include
            
        Returns:
            JsonResponse: Standardized error response
            
        Usage:
            return JsonResponseHelper.error('User not found', status=404)
        """
        response = {
            'success': False,
            'error': error_message
        }
        
        if extra_data:
            response.update(extra_data)
            
        return JsonResponse(response, status=status)
    
    @staticmethod
    def not_found(model_name):
        """
        Return standardized 'not found' response.
        
        Args:
            model_name (str): Name of the model that wasn't found
            
        Returns:
            JsonResponse: Standardized not found response
            
        Usage:
            return JsonResponseHelper.not_found('User')
        """
        return JsonResponseHelper.error(f'{model_name} not found', status=404)
    
    @staticmethod
    def method_not_allowed(allowed_methods=None):
        """
        Return standardized method not allowed response.
        
        Args:
            allowed_methods (list, optional): List of allowed methods
            
        Returns:
            JsonResponse: Method not allowed response
            
        Usage:
            return JsonResponseHelper.method_not_allowed(['POST'])
        """
        error_msg = 'Method not allowed'
        if allowed_methods:
            error_msg += f'. Allowed: {", ".join(allowed_methods)}'
            
        return JsonResponseHelper.error(error_msg, status=405)
    
    @staticmethod
    def permission_denied(message='Permission denied'):
        """
        Return standardized permission denied response.
        
        Args:
            message (str): Custom permission denied message
            
        Returns:
            JsonResponse: Permission denied response
            
        Usage:
            return JsonResponseHelper.permission_denied('Admin access required')
        """
        return JsonResponseHelper.error(message, status=403)
    
    @staticmethod
    def requires_confirmation(message, confirmation_data=None, **extra_data):
        """
        Return response requiring user confirmation.
        
        Args:
            message (str): Confirmation message
            confirmation_data (dict, optional): Data for confirmation dialog
            **extra_data: Additional fields
            
        Returns:
            JsonResponse: Confirmation required response
            
        Usage:
            return JsonResponseHelper.requires_confirmation(
                'Delete user with 5 related objects?',
                confirmation_data={'related_count': 5}
            )
        """
        response = {
            'success': False,
            'requires_confirmation': True,
            'error': message
        }
        
        if confirmation_data:
            response.update(confirmation_data)
            
        if extra_data:
            response.update(extra_data)
            
        return JsonResponse(response)


class FormResponseHelper:
    """
    Helper for form-based responses (non-AJAX).
    
    Provides consistent redirect + message patterns.
    """
    
    @staticmethod
    def success_redirect(request, redirect_url, message, **message_kwargs):
        """
        Add success message and redirect.
        
        Args:
            request: Django request object
            redirect_url (str): URL to redirect to
            message (str): Success message
            **message_kwargs: Message formatting arguments
            
        Returns:
            HttpResponseRedirect: Redirect response with message
            
        Usage:
            return FormResponseHelper.success_redirect(
                request, 'frontend:user_management',
                'User "{username}" created successfully',
                username=user.username
            )
        """
        formatted_message = message.format(**message_kwargs) if message_kwargs else message
        messages.success(request, formatted_message)
        return redirect(redirect_url)
    
    @staticmethod
    def error_redirect(request, redirect_url, error_message, **message_kwargs):
        """
        Add error message and redirect.
        
        Args:
            request: Django request object
            redirect_url (str): URL to redirect to  
            error_message (str): Error message
            **message_kwargs: Message formatting arguments
            
        Returns:
            HttpResponseRedirect: Redirect response with error message
            
        Usage:
            return FormResponseHelper.error_redirect(
                request, 'frontend:user_management',
                'Error creating user: {error}',
                error=str(e)
            )
        """
        formatted_message = error_message.format(**message_kwargs) if message_kwargs else error_message
        messages.error(request, formatted_message)
        return redirect(redirect_url)