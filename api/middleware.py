"""
Security middleware for API rate limiting and security headers.
"""

import time
from typing import Dict, Optional
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.core.cache import cache
from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from django.views.decorators.cache import never_cache
from django.utils.decorators import method_decorator


class APISecurityMiddleware(MiddlewareMixin):
    """
    Security middleware for API endpoints with rate limiting and security headers.
    """
    
    def __init__(self, get_response):
        super().__init__(get_response)
        self.get_response = get_response
        self.rate_limits = getattr(settings, 'API_RATE_LIMITS', {})
    
    def process_request(self, request: HttpRequest) -> Optional[HttpResponse]:
        """Process incoming request for rate limiting."""
        
        # Only apply to API endpoints
        if not request.path.startswith('/api/'):
            return None
        
        # Apply rate limiting based on endpoint type
        rate_limit_response = self._check_rate_limit(request)
        if rate_limit_response:
            return rate_limit_response
        
        return None
    
    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Add security headers to API responses."""
        
        # Only add headers to API responses
        if request.path.startswith('/api/'):
            response = self._add_security_headers(response)
            response = self._add_rate_limit_headers(request, response)
        
        return response
    
    def _check_rate_limit(self, request: HttpRequest) -> Optional[JsonResponse]:
        """
        Check if request should be rate limited.
        
        Returns JsonResponse with 429 status if rate limited, None otherwise.
        """
        if not getattr(settings, 'RATELIMIT_ENABLE', True):
            return None
        
        # Determine rate limit type based on request
        limit_type = self._get_rate_limit_type(request)
        if not limit_type or limit_type not in self.rate_limits:
            return None
        
        # Get rate limit configuration
        rate_config = self.rate_limits[limit_type]
        limit, period = self._parse_rate_limit(rate_config)
        
        # Generate cache key based on IP and user
        cache_key = self._get_cache_key(request, limit_type)
        
        # Check current request count
        current_count = cache.get(cache_key, 0)
        
        if current_count >= limit:
            # Rate limit exceeded
            return JsonResponse({
                'error': 'Rate limit exceeded',
                'detail': f'Too many requests. Limit: {limit} per {period} seconds.',
                'retry_after': self._get_retry_after(cache_key, period)
            }, status=429)
        
        # Increment counter
        cache.set(cache_key, current_count + 1, period)
        
        return None
    
    def _get_rate_limit_type(self, request: HttpRequest) -> Optional[str]:
        """Determine the rate limit type for the request."""
        
        # Authentication endpoints
        if '/api/auth/' in request.path:
            return 'auth'
        
        # Bulk operations
        if 'bulk' in request.path.lower() or request.path.endswith('/bulk_create/'):
            return 'api_bulk'
        
        # Write operations (POST, PUT, PATCH, DELETE)
        if request.method in ['POST', 'PUT', 'PATCH', 'DELETE']:
            return 'api_write'
        
        # Read operations (GET)
        if request.method == 'GET':
            return 'api_read'
        
        return None
    
    def _parse_rate_limit(self, rate_config: str) -> tuple[int, int]:
        """
        Parse rate limit configuration string.
        
        Format: "requests/period" where period can be 's', 'm', 'h', 'd'
        Example: "100/m" = 100 requests per minute
        """
        requests, period_str = rate_config.split('/')
        requests = int(requests)
        
        # Convert period to seconds
        period_map = {
            's': 1,      # seconds
            'm': 60,     # minutes
            'h': 3600,   # hours
            'd': 86400   # days
        }
        
        period_unit = period_str[-1]
        period_value = int(period_str[:-1]) if len(period_str) > 1 else 1
        period_seconds = period_value * period_map.get(period_unit, 60)
        
        return requests, period_seconds
    
    def _get_cache_key(self, request: HttpRequest, limit_type: str) -> str:
        """Generate cache key for rate limiting."""
        
        # Use IP address and user ID if authenticated
        ip_address = self._get_client_ip(request)
        user_id = request.user.id if request.user.is_authenticated else 'anon'
        
        return f"ratelimit:{limit_type}:{ip_address}:{user_id}"
    
    def _get_client_ip(self, request: HttpRequest) -> str:
        """Get client IP address, handling proxies."""
        
        # Check for forwarded IP (behind proxy)
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        
        # Check for real IP
        x_real_ip = request.META.get('HTTP_X_REAL_IP')
        if x_real_ip:
            return x_real_ip
        
        # Fallback to remote address
        return request.META.get('REMOTE_ADDR', '127.0.0.1')
    
    def _get_retry_after(self, cache_key: str, period: int) -> int:
        """Get the retry-after time in seconds."""
        
        # For simplicity, return the full period
        # In production, you might want to track when the limit was first hit
        return period
    
    def _add_security_headers(self, response: HttpResponse) -> HttpResponse:
        """Add security headers to API responses."""
        
        # Security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # API-specific headers
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        
        return response
    
    def _add_rate_limit_headers(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Add rate limit information headers."""
        
        limit_type = self._get_rate_limit_type(request)
        if not limit_type or limit_type not in self.rate_limits:
            return response
        
        rate_config = self.rate_limits[limit_type]
        limit, period = self._parse_rate_limit(rate_config)
        
        # Get current usage
        cache_key = self._get_cache_key(request, limit_type)
        current_count = cache.get(cache_key, 0)
        
        # Add rate limit headers
        response['X-RateLimit-Limit'] = str(limit)
        response['X-RateLimit-Remaining'] = str(max(0, limit - current_count))
        response['X-RateLimit-Reset'] = str(int(time.time()) + period)
        
        return response


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Middleware to add comprehensive security headers to all responses.
    """
    
    def process_response(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """Add security headers to all responses."""
        
        # Content Security Policy
        if hasattr(settings, 'CSP_DEFAULT_SRC'):
            csp_parts = []
            
            if hasattr(settings, 'CSP_DEFAULT_SRC'):
                csp_parts.append(f"default-src {' '.join(settings.CSP_DEFAULT_SRC)}")
            
            if hasattr(settings, 'CSP_SCRIPT_SRC'):
                csp_parts.append(f"script-src {' '.join(settings.CSP_SCRIPT_SRC)}")
            
            if hasattr(settings, 'CSP_STYLE_SRC'):
                csp_parts.append(f"style-src {' '.join(settings.CSP_STYLE_SRC)}")
            
            if hasattr(settings, 'CSP_IMG_SRC'):
                csp_parts.append(f"img-src {' '.join(settings.CSP_IMG_SRC)}")
            
            if hasattr(settings, 'CSP_CONNECT_SRC'):
                csp_parts.append(f"connect-src {' '.join(settings.CSP_CONNECT_SRC)}")
            
            if hasattr(settings, 'CSP_FONT_SRC'):
                csp_parts.append(f"font-src {' '.join(settings.CSP_FONT_SRC)}")
            
            if csp_parts:
                # Override any existing CSP header
                response['Content-Security-Policy'] = '; '.join(csp_parts)
                print("Injected CSP:", response.get('Content-Security-Policy'))
        
        # Additional security headers
        response['Permissions-Policy'] = (
            'geolocation=(), '
            'camera=(), '
            'microphone=(), '
            'payment=(), '
            'usb=(), '
            'magnetometer=(), '
            'gyroscope=(), '
            'accelerometer=()'
        )
        
        # Server identification
        response['Server'] = 'Vessel Sales System'
        
        return response


class MobileOptimizationMiddleware(MiddlewareMixin):
    """
    Middleware to optimize API responses for mobile devices.
    """
    
    MOBILE_USER_AGENTS = [
        r'Mobile', r'Android', r'iPhone', r'iPad', r'iPod',
        r'BlackBerry', r'Windows Phone', r'Opera Mini'
    ]
    
    def __init__(self, get_response):
        self.get_response = get_response
        super().__init__(get_response)
    
    def is_mobile_device(self, request):
        """Check if the request is from a mobile device."""
        import re
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        for pattern in self.MOBILE_USER_AGENTS:
            if re.search(pattern, user_agent, re.IGNORECASE):
                return True
        return False
    
    def process_request(self, request):
        """Process the request to add mobile context."""
        # Add mobile context to request
        request.is_mobile = self.is_mobile_device(request)
        
        # Adjust pagination for mobile devices
        if request.is_mobile and request.path.startswith('/api/'):
            # Reduce page size for mobile devices if not explicitly set
            if 'page_size' not in request.GET:
                # Set smaller page size for mobile
                request.GET = request.GET.copy()
                request.GET['page_size'] = '10'  # Smaller pages for mobile
        
        return None
    
    def process_response(self, request, response):
        """Process the response to optimize for mobile."""
        if hasattr(request, 'is_mobile') and request.is_mobile:
            # Add mobile optimization headers
            response['X-Mobile-Optimized'] = 'true'
            response['Cache-Control'] = 'public, max-age=300'  # Shorter cache for mobile
            
            # Compress JSON responses for mobile
            if (response.get('Content-Type', '').startswith('application/json') and
                hasattr(response, 'content') and len(response.content) > 1024):
                
                # Add compression hint
                response['X-Compression-Recommended'] = 'true'
        
        return response


class CompactResponseMiddleware(MiddlewareMixin):
    """
    Middleware to provide compact API responses when requested.
    """
    
    def process_request(self, request):
        """Check if compact response is requested."""
        request.compact_response = request.GET.get('compact', '').lower() == 'true'
        return None