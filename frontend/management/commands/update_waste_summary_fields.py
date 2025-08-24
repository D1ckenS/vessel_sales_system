from django.core.management.base import BaseCommand
from transactions.models import WasteReport


class Command(BaseCommand):
    help = 'Update pre-calculated summary fields (total_cost, item_count) for existing waste reports'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Update all waste reports, even those with existing values'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        
        self.stdout.write(self.style.SUCCESS('=== Waste Report Summary Fields Update ==='))
        
        # Find waste reports that need updating
        if force:
            queryset = WasteReport.objects.all()
            self.stdout.write(f'Force mode: Updating ALL waste reports')
        else:
            # Only update reports with missing summary data
            queryset = WasteReport.objects.filter(total_cost=0, item_count=0)
            self.stdout.write(f'Standard mode: Updating waste reports with missing summary fields')
        
        total_reports = queryset.count()
        
        if total_reports == 0:
            self.stdout.write(self.style.WARNING('No waste reports found that need updating.'))
            return
        
        self.stdout.write(f'Found {total_reports} waste reports to update')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        updated_count = 0
        
        for report in queryset:
            # Calculate current values
            current_total = float(report.total_cost)
            current_count = report.item_count
            
            # Get calculated values
            calculated_total = float(report.calculated_total_cost)
            calculated_count = report.calculated_item_count
            
            self.stdout.write(f'Report {report.report_number}:')
            self.stdout.write(f'  Current: total_cost={current_total}, item_count={current_count}')
            self.stdout.write(f'  Calculated: total_cost={calculated_total}, item_count={calculated_count}')
            
            # Check if update is needed
            needs_update = (
                force or 
                current_total != calculated_total or 
                current_count != calculated_count
            )
            
            if needs_update:
                if not dry_run:
                    report.update_summary_fields()
                    updated_count += 1
                    self.stdout.write(f'  UPDATED: New values saved')
                else:
                    updated_count += 1
                    self.stdout.write(f'  WOULD UPDATE: Changes needed')
            else:
                self.stdout.write(f'  SKIPPED: Already up to date')
            
            self.stdout.write('')  # Empty line for readability
        
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f'DRY RUN COMPLETE: {updated_count} waste reports would be updated'))
        else:
            self.stdout.write(self.style.SUCCESS(f'UPDATE COMPLETE: {updated_count} waste reports updated successfully'))
        
        self.stdout.write('')
        self.stdout.write('Summary fields updated:')
        self.stdout.write('- total_cost: Pre-calculated total cost of all waste transactions')
        self.stdout.write('- item_count: Pre-calculated count of waste transactions')