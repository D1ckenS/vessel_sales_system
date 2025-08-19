"""
Management command to assign existing users without vessel assignments to vessels.
This ensures all users have at least one vessel assignment for system access.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.db import transaction
from vessels.models import Vessel
from vessel_management.models import UserVesselAssignment


class Command(BaseCommand):
    help = 'Assign existing users without vessel assignments to appropriate vessels'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be assigned without making changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force assignment even if user already has some vessel assignments',
        )
        parser.add_argument(
            '--vessel',
            type=str,
            help='Assign all users to specific vessel (vessel name)',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        specific_vessel = options['vessel']
        
        self.stdout.write(
            self.style.SUCCESS(
                'Checking for users without vessel assignments...'
            )
        )
        
        # Get active vessels
        active_vessels = Vessel.objects.filter(active=True).order_by('name')
        if not active_vessels.exists():
            self.stdout.write(
                self.style.ERROR('No active vessels found. Cannot assign users.')
            )
            return
        
        # Use specific vessel if provided
        if specific_vessel:
            try:
                target_vessel = active_vessels.get(name=specific_vessel)
                vessels_to_use = [target_vessel]
                self.stdout.write(
                    self.style.WARNING(f'Using specific vessel: {target_vessel.name}')
                )
            except Vessel.DoesNotExist:
                self.stdout.write(
                    self.style.ERROR(f'Vessel "{specific_vessel}" not found or not active.')
                )
                return
        else:
            vessels_to_use = list(active_vessels)
            first_vessel = vessels_to_use[0]
        
        # Find users without assignments
        if force:
            users_without_assignments = User.objects.all()
            self.stdout.write(
                self.style.WARNING('Force mode: Processing all users')
            )
        else:
            # Users with no vessel assignments at all
            assigned_user_ids = UserVesselAssignment.objects.values_list('user_id', flat=True).distinct()
            users_without_assignments = User.objects.exclude(id__in=assigned_user_ids)
        
        if not users_without_assignments.exists():
            self.stdout.write(
                self.style.SUCCESS('All users already have vessel assignments.')
            )
            return
        
        # Count and display what will be processed
        total_users = users_without_assignments.count()
        self.stdout.write(f'Found {total_users} users without vessel assignments:')
        
        assignments_to_create = []
        
        for user in users_without_assignments:
            if user.is_superuser:
                # SuperUsers get automatic access, no assignment needed
                self.stdout.write(f'  - {user.username} (SuperUser): Automatic access, no assignment needed')
                continue
            
            if specific_vessel:
                # Assign to specific vessel
                vessels_for_user = [target_vessel]
                assignment_reason = f'Assigned to {target_vessel.name} via management command'
            elif user.is_staff:
                # Staff users (Admins/Managers) get access to all active vessels
                vessels_for_user = vessels_to_use
                assignment_reason = 'Staff user - assigned to all active vessels via management command'
            else:
                # Regular users get assigned to first active vessel
                vessels_for_user = [first_vessel]
                assignment_reason = f'Regular user - assigned to {first_vessel.name} via management command'
            
            for vessel in vessels_for_user:
                if not force:
                    # Check if assignment already exists
                    existing = UserVesselAssignment.objects.filter(
                        user=user, vessel=vessel
                    ).exists()
                    if existing:
                        self.stdout.write(f'  - {user.username} → {vessel.name}: Already assigned, skipping')
                        continue
                
                assignment_data = {
                    'user': user,
                    'vessel': vessel,
                    'is_active': True,
                    'can_make_sales': True,
                    'can_receive_inventory': True,
                    'can_initiate_transfers': True,
                    'can_approve_transfers': True,
                    'notes': assignment_reason
                }
                
                assignments_to_create.append(assignment_data)
                self.stdout.write(f'  - {user.username} → {vessel.name}: Will be assigned')
        
        if not assignments_to_create:
            self.stdout.write(
                self.style.SUCCESS('No new assignments needed.')
            )
            return
        
        # Show summary
        self.stdout.write(f'\nTotal assignments to create: {len(assignments_to_create)}')
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN: No changes made. Use --dry-run=False to apply changes.')
            )
            return
        
        # Create assignments
        try:
            with transaction.atomic():
                created_count = 0
                for assignment_data in assignments_to_create:
                    assignment, created = UserVesselAssignment.objects.get_or_create(
                        user=assignment_data['user'],
                        vessel=assignment_data['vessel'],
                        defaults={
                            'is_active': assignment_data['is_active'],
                            'can_make_sales': assignment_data['can_make_sales'],
                            'can_receive_inventory': assignment_data['can_receive_inventory'],
                            'can_initiate_transfers': assignment_data['can_initiate_transfers'],
                            'can_approve_transfers': assignment_data['can_approve_transfers'],
                            'notes': assignment_data['notes']
                        }
                    )
                    if created:
                        created_count += 1
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully created {created_count} vessel assignments.'
                    )
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error creating assignments: {str(e)}')
            )
            raise
        
        # Final verification
        remaining_unassigned = User.objects.exclude(
            id__in=UserVesselAssignment.objects.values_list('user_id', flat=True).distinct()
        ).exclude(is_superuser=True).count()
        
        if remaining_unassigned == 0:
            self.stdout.write(
                self.style.SUCCESS('✅ All users now have vessel assignments!')
            )
        else:
            self.stdout.write(
                self.style.WARNING(f'⚠️ {remaining_unassigned} users still without assignments')
            )