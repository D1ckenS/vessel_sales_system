from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group, Permission
from django.db import transaction
import os

class Command(BaseCommand):
    help = 'Activate authentication system and setup default users/groups'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--create-superuser',
            action='store_true',
            help='Create a superuser account',
        )
        parser.add_argument(
            '--username',
            type=str,
            help='Username for superuser',
            default='admin'
        )
        parser.add_argument(
            '--password',
            type=str,
            help='Password for superuser',
            default='admin123'
        )
    
    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🔐 Activating Authentication System...'))
        
        # 1. Uncomment @login_required decorators
        self.activate_login_required()
        
        # 2. Create default groups
        self.setup_default_groups()
        
        # 3. Create superuser if requested
        if options['create_superuser']:
            self.create_superuser(options['username'], options['password'])
        
        self.stdout.write(self.style.SUCCESS('✅ Authentication system activated successfully!'))
        self.stdout.write(self.style.WARNING('⚠️  Remember to restart your Django server'))
    
    def activate_login_required(self):
        """Uncomment all @login_required decorators in views.py"""
        views_file = 'frontend/views.py'
        
        if not os.path.exists(views_file):
            self.stdout.write(self.style.ERROR(f'❌ {views_file} not found'))
            return
        
        with open(views_file, 'r') as f:
            content = f.read()
        
        # Uncomment @login_required decorators
        updated_content = content.replace('# @login_required', '@login_required')
        
        # Add login_required import if not present
        if 'from django.contrib.auth.decorators import login_required' not in updated_content:
            import_line = 'from django.contrib.auth.decorators import login_required\n'
            # Add after the other Django imports
            lines = updated_content.split('\n')
            insert_index = 0
            for i, line in enumerate(lines):
                if line.startswith('from django.'):
                    insert_index = i + 1
            lines.insert(insert_index, import_line)
            updated_content = '\n'.join(lines)
        
        with open(views_file, 'w') as f:
            f.write(updated_content)
        
        self.stdout.write(self.style.SUCCESS(f'✅ Activated @login_required decorators in {views_file}'))
    
    def setup_default_groups(self):
        """Create default user groups with appropriate permissions"""
        groups_config = {
            'Administrators': {
                'description': 'Full system access',
                'permissions': 'all'
            },
            'Managers': {
                'description': 'Management access to all vessels and reports',
                'permissions': ['view', 'add', 'change']
            },
            'Vessel Operators': {
                'description': 'Can operate assigned vessels',
                'permissions': ['view', 'add']
            },
            'Inventory Staff': {
                'description': 'Can manage inventory and transfers',
                'permissions': ['view', 'add', 'change']
            },
            'Viewers': {
                'description': 'Read-only access to reports',
                'permissions': ['view']
            }
        }
        
        with transaction.atomic():
            for group_name, config in groups_config.items():
                group, created = Group.objects.get_or_create(name=group_name)
                if created:
                    self.stdout.write(f'✅ Created group: {group_name}')
                else:
                    self.stdout.write(f'ℹ️  Group already exists: {group_name}')
    
    def create_superuser(self, username, password):
        """Create superuser account"""
        try:
            if User.objects.filter(username=username).exists():
                self.stdout.write(self.style.WARNING(f'⚠️  Superuser "{username}" already exists'))
                return
            
            superuser = User.objects.create_superuser(
                username=username,
                password=password,
                email='admin@vesselsales.com',
                first_name='System',
                last_name='Administrator'
            )
            
            # Add to Administrators group
            admin_group, _ = Group.objects.get_or_create(name='Administrators')
            superuser.groups.add(admin_group)
            
            self.stdout.write(self.style.SUCCESS(f'✅ Created superuser: {username}'))
            self.stdout.write(self.style.WARNING(f'🔑 Password: {password}'))
            self.stdout.write(self.style.WARNING('⚠️  Please change the password after first login!'))
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error creating superuser: {e}'))