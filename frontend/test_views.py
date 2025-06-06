# frontend/test_views.py - Temporary file for testing authentication styling

from django.shortcuts import render
from django.contrib.auth.models import User, Group

def test_login(request):
    """Test the login template styling"""
    return render(request, 'frontend/auth/login.html')

def test_user_management(request):
    """Test the user management template styling"""
    
    # Create some fake data for testing
    fake_users = []
    try:
        # Get real users if they exist
        users = User.objects.all()[:5]  # Get first 5 users
        if not users.exists():
            # Create fake user data for display
            class FakeUser:
                def __init__(self, username, email, first_name, last_name, is_active, is_staff, is_superuser):
                    self.username = username
                    self.email = email
                    self.first_name = first_name
                    self.last_name = last_name
                    self.is_active = is_active
                    self.is_staff = is_staff
                    self.is_superuser = is_superuser
                    self.last_login = None
                    self.date_joined = "2025-01-01 10:00:00"
                    
                def get_full_name(self):
                    return f"{self.first_name} {self.last_name}".strip()
                
                @property
                def groups(self):
                    class FakeGroups:
                        def all(self):
                            return []
                    return FakeGroups()
            
            fake_users = [
                FakeUser("admin", "admin@vesselsales.com", "System", "Administrator", True, True, True),
                FakeUser("captain", "captain@vesselsales.com", "John", "Smith", True, True, False),
                FakeUser("operator", "operator@vesselsales.com", "Sarah", "Johnson", True, False, False),
                FakeUser("viewer", "viewer@vesselsales.com", "Mike", "Wilson", False, False, False),
            ]
        else:
            fake_users = users
            
    except:
        # Fallback fake data
        class FakeUser:
            def __init__(self, username, email, first_name, last_name, is_active, is_staff, is_superuser):
                self.username = username
                self.email = email
                self.first_name = first_name
                self.last_name = last_name
                self.is_active = is_active
                self.is_staff = is_staff
                self.is_superuser = is_superuser
                self.last_login = None
                self.date_joined = "2025-01-01 10:00:00"
                
            def get_full_name(self):
                return f"{self.first_name} {self.last_name}".strip()
            
            @property
            def groups(self):
                class FakeGroups:
                    def all(self):
                        return []
                return FakeGroups()
        
        fake_users = [
            FakeUser("admin", "admin@vesselsales.com", "System", "Administrator", True, True, True),
            FakeUser("captain", "captain@vesselsales.com", "John", "Smith", True, True, False),
            FakeUser("operator", "operator@vesselsales.com", "Sarah", "Johnson", True, False, False),
            FakeUser("viewer", "viewer@vesselsales.com", "Mike", "Wilson", False, False, False),
        ]
    
    # Get or create fake groups
    try:
        groups = Group.objects.all()
        if not groups.exists():
            # Create fake groups for testing
            class FakeGroup:
                def __init__(self, name):
                    self.name = name
                    self.id = hash(name) % 1000
            
            groups = [
                FakeGroup("Administrators"),
                FakeGroup("Managers"),
                FakeGroup("Vessel Operators"),
                FakeGroup("Inventory Staff"),
                FakeGroup("Viewers"),
            ]
    except:
        class FakeGroup:
            def __init__(self, name):
                self.name = name
                self.id = hash(name) % 1000
        
        groups = [
            FakeGroup("Administrators"),
            FakeGroup("Managers"),
            FakeGroup("Vessel Operators"),
            FakeGroup("Inventory Staff"),
            FakeGroup("Viewers"),
        ]
    
    context = {
        'users': fake_users,
        'groups': groups,
    }
    
    return render(request, 'frontend/auth/user_management.html', context)

def test_change_password(request):
    """Test the change password template styling"""
    return render(request, 'frontend/auth/change_password.html')

def test_user_profile(request):
    """Test the user profile template styling"""
    
    # Create fake user data
    class FakeUser:
        username = "testuser"
        email = "test@vesselsales.com"
        first_name = "Test"
        last_name = "User"
        is_active = True
        is_staff = True
        is_superuser = False
        last_login = "2025-06-06 14:30:00"
        date_joined = "2025-01-01 10:00:00"
        
        def get_full_name(self):
            return "Test User"
        
        @property
        def groups(self):
            class FakeGroups:
                def all(self):
                    class FakeGroup:
                        def __init__(self, name):
                            self.name = name
                    return [FakeGroup("Managers"), FakeGroup("Vessel Operators")]
            return FakeGroups()
    
    class FakeGroup:
        def __init__(self, name):
            self.name = name
    
    fake_user_groups = [FakeGroup("Managers"), FakeGroup("Vessel Operators")]
    
    context = {
        'user': FakeUser(),
        'user_groups': fake_user_groups,
    }
    
    return render(request, 'frontend/auth/user_profile.html', context)