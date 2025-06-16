#!/usr/bin/env python3
"""
Secret Key Generator for Vessel Sales System
Generate secure Django secret keys for production use.
"""

import secrets
import string
from django.core.management.utils import get_random_secret_key

def generate_django_secret_key():
    """Generate a secure Django secret key"""
    return get_random_secret_key()

def generate_custom_secret_key(length=50):
    """Generate a custom secure secret key"""
    alphabet = string.ascii_letters + string.digits + '!@$%^&*(-_+)'
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def main():
    print("🔐 Vessel Sales System - Secret Key Generator")
    print("=" * 50)
    
    print("\n1. Django Standard Secret Key:")
    django_key = generate_django_secret_key()
    print(f"   {django_key}")
    
    print("\n2. Custom Secret Key (50 chars):")
    custom_key = generate_custom_secret_key()
    print(f"   {custom_key}")
    
    print("\n📋 Instructions:")
    print("1. Copy one of the secret keys above")
    print("2. Add it to your .env file as DJANGO_SECRET_KEY=your-key-here")
    print("3. Never share or commit this key to version control!")
    print("4. Use different keys for development and production")
    
    print("\n⚠️  SECURITY REMINDERS:")
    print("• Keep secret keys confidential")
    print("• Use environment variables in production") 
    print("• Rotate keys periodically")
    print("• Never hardcode keys in source code")

if __name__ == "__main__":
    try:
        main()
    except ImportError:
        print("Error: Django not found. Please install Django first:")
        print("pip install django")
        
        # Fallback without Django
        print("\nFallback secret key (without Django):")
        fallback_key = generate_custom_secret_key()
        print(f"   {fallback_key}")