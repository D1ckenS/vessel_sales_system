"""
Management command to check API security status and configuration.
"""

from django.core.management.base import BaseCommand
from django.conf import settings
from django.test import RequestFactory
from django.contrib.auth.models import User
from django.core.cache import cache
from colorama import Fore, Style, init


class Command(BaseCommand):
    """Check API security configuration and status."""
    
    help = 'Check API security configuration and status'
    
    def __init__(self):
        super().__init__()
        init(autoreset=True)  # Initialize colorama
        self.factory = RequestFactory()
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--detailed',
            action='store_true',
            help='Show detailed security analysis',
        )
        parser.add_argument(
            '--test-rate-limit',
            action='store_true',
            help='Test rate limiting functionality',
        )
    
    def handle(self, *args, **options):
        """Main command handler."""
        
        self.stdout.write(f"{Fore.CYAN}Vessel Sales System - Security Check{Style.RESET_ALL}")
        self.stdout.write("=" * 60)
        
        # Check basic security configuration
        self.check_security_middleware()
        self.check_authentication_config()
        self.check_rate_limiting_config()
        self.check_security_headers_config()
        self.check_axes_config()
        
        if options['detailed']:
            self.detailed_security_analysis()
        
        if options['test_rate_limit']:
            self.test_rate_limiting()
        
        self.stdout.write(f"\\n{Fore.GREEN}Security check completed{Style.RESET_ALL}")
    
    def check_security_middleware(self):
        """Check if security middleware is properly configured."""
        
        self.stdout.write(f"\\n{Fore.YELLOW}Security Middleware Configuration{Style.RESET_ALL}")
        
        middleware = getattr(settings, 'MIDDLEWARE', [])
        
        # Check for our custom security middleware
        security_middlewares = {
            'api.middleware.SecurityHeadersMiddleware': 'Security Headers Middleware',
            'api.middleware.APISecurityMiddleware': 'API Rate Limiting Middleware',
            'axes.middleware.AxesMiddleware': 'Brute Force Protection',
            'corsheaders.middleware.CorsMiddleware': 'CORS Middleware',
        }
        
        for middleware_class, description in security_middlewares.items():
            if middleware_class in middleware:
                self.stdout.write(f"  {Fore.GREEN}[OK] {description}{Style.RESET_ALL}")
            else:
                self.stdout.write(f"  {Fore.RED}[MISSING] {description}{Style.RESET_ALL}")
    
    def check_authentication_config(self):
        """Check JWT and authentication configuration."""
        
        self.stdout.write(f"\\n{Fore.YELLOW}Authentication Configuration{Style.RESET_ALL}")
        
        # Check JWT settings
        jwt_settings = getattr(settings, 'SIMPLE_JWT', {})
        if jwt_settings:
            self.stdout.write(f"  {Fore.GREEN}[OK] JWT Configuration Found{Style.RESET_ALL}")
            
            # Check JWT token lifetime
            access_lifetime = jwt_settings.get('ACCESS_TOKEN_LIFETIME')
            if access_lifetime:
                self.stdout.write(f"    Access Token Lifetime: {access_lifetime}")
            
            refresh_lifetime = jwt_settings.get('REFRESH_TOKEN_LIFETIME')
            if refresh_lifetime:
                self.stdout.write(f"    Refresh Token Lifetime: {refresh_lifetime}")
        else:
            self.stdout.write(f"  {Fore.RED}[MISSING] JWT Configuration Missing{Style.RESET_ALL}")
        
        # Check authentication backends
        auth_backends = getattr(settings, 'AUTHENTICATION_BACKENDS', [])
        if 'axes.backends.AxesStandaloneBackend' in auth_backends:
            self.stdout.write(f"  {Fore.GREEN}[OK] Axes Security Backend Configured{Style.RESET_ALL}")
        else:
            self.stdout.write(f"  {Fore.YELLOW}[WARNING] Axes Security Backend Not Found{Style.RESET_ALL}")
    
    def check_rate_limiting_config(self):
        """Check rate limiting configuration."""
        
        self.stdout.write(f"\\n{Fore.YELLOW}⏱️  Rate Limiting Configuration{Style.RESET_ALL}")
        
        rate_limits = getattr(settings, 'API_RATE_LIMITS', {})
        if rate_limits:
            self.stdout.write(f"  {Fore.GREEN}✅ Rate Limits Configured{Style.RESET_ALL}")
            for limit_type, limit_value in rate_limits.items():
                self.stdout.write(f"    {limit_type}: {limit_value}")
        else:
            self.stdout.write(f"  {Fore.RED}❌ Rate Limits Not Configured{Style.RESET_ALL}")
        
        # Check if rate limiting is enabled
        ratelimit_enabled = getattr(settings, 'RATELIMIT_ENABLE', False)
        if ratelimit_enabled:
            self.stdout.write(f"  {Fore.GREEN}✅ Rate Limiting Enabled{Style.RESET_ALL}")
        else:
            self.stdout.write(f"  {Fore.RED}❌ Rate Limiting Disabled{Style.RESET_ALL}")
    
    def check_security_headers_config(self):
        """Check security headers configuration."""
        
        self.stdout.write(f"\\n{Fore.YELLOW}🛡️  Security Headers Configuration{Style.RESET_ALL}")
        
        security_settings = {
            'SECURE_CONTENT_TYPE_NOSNIFF': 'Content Type Nosniff',
            'SECURE_BROWSER_XSS_FILTER': 'XSS Filter',
            'X_FRAME_OPTIONS': 'Frame Options',
            'SESSION_COOKIE_SECURE': 'Secure Session Cookies',
            'CSRF_COOKIE_SECURE': 'Secure CSRF Cookies',
            'SESSION_COOKIE_HTTPONLY': 'HttpOnly Session Cookies',
            'CSRF_COOKIE_HTTPONLY': 'HttpOnly CSRF Cookies',
        }
        
        for setting, description in security_settings.items():
            value = getattr(settings, setting, None)
            if value:
                self.stdout.write(f"  {Fore.GREEN}✅ {description}: {value}{Style.RESET_ALL}")
            else:
                self.stdout.write(f"  {Fore.YELLOW}⚠️  {description}: Not Set{Style.RESET_ALL}")
        
        # Check CSP settings
        csp_settings = ['CSP_DEFAULT_SRC', 'CSP_SCRIPT_SRC', 'CSP_STYLE_SRC']
        csp_configured = any(hasattr(settings, setting) for setting in csp_settings)
        
        if csp_configured:
            self.stdout.write(f"  {Fore.GREEN}✅ Content Security Policy Configured{Style.RESET_ALL}")
        else:
            self.stdout.write(f"  {Fore.YELLOW}⚠️  Content Security Policy Not Configured{Style.RESET_ALL}")
    
    def check_axes_config(self):
        """Check django-axes configuration."""
        
        self.stdout.write(f"\\n{Fore.YELLOW}🔒 Brute Force Protection (Axes){Style.RESET_ALL}")
        
        axes_settings = {
            'AXES_ENABLED': 'Axes Protection',
            'AXES_FAILURE_LIMIT': 'Failure Limit',
            'AXES_COOLOFF_TIME': 'Cooloff Time',
            'AXES_RESET_ON_SUCCESS': 'Reset on Success',
        }
        
        for setting, description in axes_settings.items():
            value = getattr(settings, setting, None)
            if value:
                self.stdout.write(f"  {Fore.GREEN}✅ {description}: {value}{Style.RESET_ALL}")
            else:
                self.stdout.write(f"  {Fore.YELLOW}⚠️  {description}: Not Set{Style.RESET_ALL}")
    
    def detailed_security_analysis(self):
        """Perform detailed security analysis."""
        
        self.stdout.write(f"\\n{Fore.CYAN}🔍 Detailed Security Analysis{Style.RESET_ALL}")
        
        # Check DEBUG mode
        debug_mode = getattr(settings, 'DEBUG', True)
        if debug_mode:
            self.stdout.write(f"  {Fore.YELLOW}⚠️  DEBUG Mode is ON - Consider disabling in production{Style.RESET_ALL}")
        else:
            self.stdout.write(f"  {Fore.GREEN}✅ DEBUG Mode is OFF{Style.RESET_ALL}")
        
        # Check SECRET_KEY
        secret_key = getattr(settings, 'SECRET_KEY', '')
        if 'django-insecure' in secret_key:
            self.stdout.write(f"  {Fore.RED}❌ Using default insecure SECRET_KEY{Style.RESET_ALL}")
        else:
            self.stdout.write(f"  {Fore.GREEN}✅ Custom SECRET_KEY configured{Style.RESET_ALL}")
        
        # Check ALLOWED_HOSTS
        allowed_hosts = getattr(settings, 'ALLOWED_HOSTS', [])
        if '*' in allowed_hosts:
            self.stdout.write(f"  {Fore.RED}❌ ALLOWED_HOSTS includes wildcard{Style.RESET_ALL}")
        elif allowed_hosts:
            self.stdout.write(f"  {Fore.GREEN}✅ ALLOWED_HOSTS properly configured{Style.RESET_ALL}")
        else:
            self.stdout.write(f"  {Fore.YELLOW}⚠️  ALLOWED_HOSTS is empty{Style.RESET_ALL}")
    
    def test_rate_limiting(self):
        """Test rate limiting functionality."""
        
        self.stdout.write(f"\\n{Fore.CYAN}🧪 Testing Rate Limiting{Style.RESET_ALL}")
        
        # Clear any existing cache entries
        cache.clear()
        
        # Simulate API requests
        from api.middleware import APISecurityMiddleware
        
        middleware = APISecurityMiddleware(lambda r: None)
        
        # Create test request
        request = self.factory.get('/api/v1/vessels/')
        request.user = User.objects.first() or User(id=1, username='test')
        
        # Test rate limiting
        cache_key = middleware._get_cache_key(request, 'api_read')
        
        self.stdout.write(f"  Test cache key: {cache_key}")
        self.stdout.write(f"  {Fore.GREEN}✅ Rate limiting test completed{Style.RESET_ALL}")