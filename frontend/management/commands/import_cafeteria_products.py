# frontend/management/commands/import_cafeteria_products.py

import csv
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from products.models import Product, Category
from django.contrib.auth.models import User


class Command(BaseCommand):
    help = 'Import cafeteria products from CSV file (item_id,name,category,purchase_price,selling_price,is_duty_free)'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to CSV file')
        parser.add_argument(
            '--dry-run', 
            action='store_true',
            help='Test import without making changes'
        )

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('🧪 DRY RUN MODE - No changes will be made'))

        # Get admin user for created_by field
        admin_user = User.objects.filter(is_superuser=True).first()
        if not admin_user:
            raise CommandError('No superuser found. Please create a superuser first.')

        # Read and process CSV
        products_data = self.read_csv(csv_file)
        self.stdout.write(f'📁 Found {len(products_data)} products to import')

        # Process in transaction
        with transaction.atomic():
            stats = {
                'products_created': 0,
                'products_updated': 0, 
                'categories_created': 0,
                'errors': 0
            }

            # Track categories to avoid repeated lookups
            categories_cache = {}

            for i, product_data in enumerate(products_data, 1):
                try:
                    # Get or create category
                    category_name = product_data['category']
                    if category_name not in categories_cache:
                        if not dry_run:
                            category, created = Category.objects.get_or_create(
                                name=category_name,
                                defaults={
                                    'description': f'Auto-created for {category_name} products',
                                    'active': True
                                }
                            )
                            if created:
                                stats['categories_created'] += 1
                                self.stdout.write(f'📂 Created category: {category_name}')
                        else:
                            category = None
                            
                        categories_cache[category_name] = category

                    category = categories_cache[category_name]

                    # Process product
                    result = self.process_product(product_data, category, admin_user, dry_run)
                    stats[f'products_{result}'] += 1
                        
                    if i % 50 == 0:
                        self.stdout.write(f'⏳ Processed {i}/{len(products_data)} products...')
                        
                except Exception as e:
                    stats['errors'] += 1
                    self.stdout.write(
                        self.style.ERROR(f'❌ Error processing row {i} (ID: {product_data.get("item_id", "unknown")}): {str(e)}')
                    )

            # Print summary
            self.stdout.write(self.style.SUCCESS('\n🎉 Import Summary:'))
            self.stdout.write(f'✅ Products created: {stats["products_created"]}')
            self.stdout.write(f'🔄 Products updated: {stats["products_updated"]}')
            self.stdout.write(f'📂 Categories created: {stats["categories_created"]}')
            if stats['errors'] > 0:
                self.stdout.write(self.style.WARNING(f'⚠️  Errors: {stats["errors"]}'))

            if dry_run:
                self.stdout.write(self.style.WARNING('\n🧪 DRY RUN COMPLETE - Rolling back all changes'))
                transaction.set_rollback(True)
            else:
                self.stdout.write(self.style.SUCCESS('\n💾 All changes saved to database!'))

    def read_csv(self, file_path):
        """Read CSV file with proper encoding detection for Arabic text"""
        products = []
        
        # Try different encodings to handle Excel CSV variations
        encodings = ['utf-8-sig', 'utf-8', 'cp1252', 'latin1']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as file:
                    reader = csv.DictReader(file)
                    
                    # Clean fieldnames (remove BOM, spaces, quotes)
                    clean_fieldnames = []
                    for field in reader.fieldnames:
                        clean_field = field.strip().strip('"').strip("'")
                        clean_fieldnames.append(clean_field)
                    
                    self.stdout.write(f'📋 Raw CSV columns: {reader.fieldnames}')
                    self.stdout.write(f'📋 Clean CSV columns: {clean_fieldnames}')
                    
                    # Validate required columns
                    required_columns = {'item_id', 'name', 'category', 'purchase_price', 'selling_price', 'is_duty_free'}
                    missing_columns = required_columns - set(clean_fieldnames)
                    
                    if missing_columns:
                        self.stdout.write(f'⚠️  Encoding {encoding} - Missing columns: {missing_columns}')
                        continue
                    
                    self.stdout.write(f'✅ Successfully reading with {encoding} encoding')
                    
                    # Re-read with clean fieldnames
                    file.seek(0)
                    reader = csv.DictReader(file)
                    
                    # Override fieldnames with clean versions
                    reader.fieldnames = clean_fieldnames

                    for row_num, row in enumerate(reader, 2):
                        # Skip empty rows
                        if not any(row.values()):
                            continue
                        
                        # Skip header row if it got mixed in with data
                        if row['item_id'].strip().lower() == 'item_id':
                            continue
                            
                        # Validate required fields
                        if not row['item_id'].strip() or not row['name'].strip():
                            self.stdout.write(
                                self.style.WARNING(f'⚠️  Skipping row {row_num}: missing item_id or name')
                            )
                            continue
                        
                        products.append({
                            'item_id': row['item_id'].strip(),
                            'name': row['name'].strip(),
                            'category': row['category'].strip() or 'General',
                            'purchase_price': row['purchase_price'].strip(),
                            'selling_price': row['selling_price'].strip(),
                            'is_duty_free': row['is_duty_free'].strip().upper()
                        })
                    
                    return products  # Success!
                    
            except Exception as e:
                self.stdout.write(f'❌ Failed with {encoding}: {e}')
                continue
        
        # If we get here, all encodings failed
        raise CommandError(
            f'Could not read CSV file with any encoding. Tried: {encodings}\n'
            'Please save your Excel file as "CSV UTF-8" format.'
        )

    def process_product(self, product_data, category, admin_user, dry_run):
        """Process a single product"""
        
        item_id = product_data['item_id']
        name = product_data['name']
        
        # Validate and convert numeric fields
        try:
            purchase_price = Decimal(str(product_data['purchase_price']))
            selling_price = Decimal(str(product_data['selling_price']))
            
            if purchase_price < 0 or selling_price < 0:
                raise ValueError('Prices cannot be negative')
                
        except (ValueError, TypeError) as e:
            raise ValueError(f'Invalid price data: {str(e)}')

        # Convert is_duty_free to boolean
        is_duty_free_str = product_data['is_duty_free']
        if is_duty_free_str in ['TRUE', 'True', '1', 'YES', 'Yes']:
            is_duty_free = True
        elif is_duty_free_str in ['FALSE', 'False', '0', 'NO', 'No']:
            is_duty_free = False
        else:
            raise ValueError(f'Invalid is_duty_free value: {is_duty_free_str}. Expected TRUE/FALSE')

        # Check if product exists
        existing_product = Product.objects.filter(item_id=item_id).first()
        
        if dry_run:
            if existing_product:
                self.stdout.write(f'🔄 Would update: {item_id} - {name}')
                return 'updated'
            else:
                self.stdout.write(f'✨ Would create: {item_id} - {name}')
                return 'created'

        if existing_product:
            # Update existing product
            existing_product.name = name
            existing_product.category = category
            existing_product.purchase_price = purchase_price
            existing_product.selling_price = selling_price
            existing_product.is_duty_free = is_duty_free
            existing_product.active = True  # Reactivate if was inactive
            existing_product.save()
            
            self.stdout.write(f'🔄 Updated: {item_id} - {name}')
            return 'updated'
        else:
            # Create new product (quantity stays at 0 as requested)
            Product.objects.create(
                name=name,
                item_id=item_id,
                category=category,
                purchase_price=purchase_price,
                selling_price=selling_price,
                is_duty_free=is_duty_free,
                active=True,
                created_by=admin_user
            )
            
            self.stdout.write(f'✨ Created: {item_id} - {name}')
            return 'created'