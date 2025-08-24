# CLAUDE.md - Vessel Sales System

## Project Overview
Professional Django-based vessel sales management system with sophisticated FIFO inventory tracking, multi-vessel operations, comprehensive reporting, and modern UI components. Built for maritime tourism operations with duty-free sales capabilities.

## System Architecture

### Core Applications (5 Django Apps)
- **`vessels/`** - Vessel management with duty-free/touristic classification and multilingual support
- **`products/`** - Product catalog with dynamic pricing rules and category management
- **`transactions/`** - Advanced FIFO inventory tracking with atomic operations and integrity validation
- **`frontend/`** - Main application UI with 20+ specialized view modules and comprehensive business logic
- **`vessel_management/`** - ⭐ NEW: User-vessel assignments, transfer workflows, and collaborative approval systems

### Key Models & Database Design

#### Core Transaction System
```python
class Transaction(models.Model):
    # Central inventory movement model with atomic FIFO
    # Types: SUPPLY/SALE/TRANSFER_IN/TRANSFER_OUT/WASTE
    # Supports vessel-specific operations and group workflows

class InventoryLot(models.Model):
    # FIFO tracking with purchase dates/costs
    # Advanced constraints ensure data integrity
    # Optimized indexes for performance

class FIFOConsumption(models.Model):
    # Dedicated FIFO consumption tracking
    # Replaces fragile string parsing with structured data
```

#### Business Entities
```python
class Vessel(models.Model):
    # Multi-language support (English/Arabic)
    # Duty-free classification for specialized pricing

class Product(models.Model):
    # Dynamic pricing with vessel-specific rules
    # Category-based organization
    # Duty-free product designation

# Group Workflow Models
class Trip, PurchaseOrder, Transfer, WasteReport
    # Two-step workflows: Create group → add items
    # Completion tracking and status management

# Transfer Workflow System (NEW - August 2025)
class TransferWorkflow, TransferItemEdit, TransferApprovalHistory, TransferNotification
    # Collaborative two-party transfer approval system
    # Real-time notifications and quantity editing
    # Complete audit trail and mutual agreement tracking

# User-Vessel Management System (NEW - August 2025)  
class UserVesselAssignment, InventoryLotStatus
    # Vessel-based access control and permission system
    # Multi-vessel support for elevated user roles
    # Smart vessel auto-population and assignment tracking
```

## Technical Features

### Database Integrity & Performance
- **Advanced Constraints**: 20+ database constraints prevent data corruption
- **Optimized Indexes**: Strategic indexing for FIFO operations and reporting
- **Atomic Transactions**: Database-level locking ensures FIFO consistency
- **Migration System**: 23+ migrations with integrity fixes and performance optimizations
- **Workflow Validation**: Enterprise-grade collaborative approval constraints

### FIFO Inventory Management
```bash
# FIFO Operations Flow
SUPPLY/TRANSFER_IN → Creates InventoryLots (purchase batches)
SALE/TRANSFER_OUT/WASTE → Consumes InventoryLots (oldest first)
FIFOConsumption → Tracks consumption details
```

### Management Commands (12+ Commands)
```bash
python manage.py activate_auth                # Setup authentication system
python manage.py rebuild_inventory_lots       # Fix inventory integrity
python manage.py check_db_integrity          # Verify data consistency
python manage.py reconcile_inventory         # Fix FIFO discrepancies
python manage.py verify_inventory_rebuild    # Validate rebuild operations
python manage.py monitor_cache              # Performance monitoring
python manage.py assign_unassigned_users     # ⭐ NEW: Handle user vessel assignments
# + 5 additional utility commands
```

## Frontend Architecture

### Modern UI System ✅
- **Unified Dropdown Design**: Professional Bootstrap components across 40+ templates
- **Universal Z-Index Management**: Centralized dropdown behavior with counter system
- **Product Search**: Real-time filtering with advanced search capabilities
- **Responsive Design**: Mobile-first approach with RTL language support
- **Professional Styling**: Enhanced shadows, animations, and hover effects

### View Organization (20+ Specialized Views)
```
frontend/
├── auth_views.py         # Authentication & user management
├── sales_views.py        # Sales operations & trip management
├── supply_views.py       # Inventory supply operations
├── transfer_views.py     # Inter-vessel transfers
├── transfer_workflow_views.py # ⭐ NEW: Collaborative workflow system
├── waste_views.py        # Waste tracking & reporting
├── product_views.py      # Product catalog management
├── vessel_views.py       # Vessel operations
├── reports_views.py      # Comprehensive reporting
├── export_views.py       # Data export functionality
├── transaction_views.py  # Transaction management
├── user_views.py         # User account operations
├── group_views.py        # Group management
├── po_views.py           # Purchase order operations
├── trip_views.py         # Trip-specific operations
├── category_views.py     # Product categorization
├── pricing_views.py      # Dynamic pricing management
├── inventory_views.py    # Inventory tracking & validation
├── waste_management_views.py   # Advanced waste operations
└── transfer_management_views.py # Transfer coordination
```

### Utility Framework (11 Helper Modules)
```
frontend/utils/
├── cache_helpers.py      # Versioned cache management
├── query_helpers.py      # Database query optimization
├── validation_helpers.py # Data validation framework
├── error_helpers.py      # Structured error handling
├── crud_helpers.py       # CRUD operation abstractions
├── exports.py            # Export functionality
├── weasy_exporter.py     # PDF generation
├── response_helpers.py   # HTTP response utilities
├── helpers.py            # General utilities
├── aggregators.py        # Data aggregation
└── __init__.py
```

### Frontend Assets
- **JavaScript**: 10 specialized modules with dropdown system integration
- **CSS**: 8 stylesheets with modern component library and RTL support
- **Templates**: 40+ HTML templates with consistent Bootstrap styling

## Unified Dropdown System ✅ (Recently Implemented)

### Implementation Complete
- **8 Key Templates** converted to professional Bootstrap dropdowns
- **Universal Z-Index Management** with sophisticated counter system
- **Enhanced Styling** with professional shadows and animations
- **Product Search Field** with real-time filtering capabilities
- **JavaScript Fixes** resolving inventory_check.js issues

### Technical Architecture
```javascript
// Universal dropdown management system
function setupUniversalDropdownZIndex(dropdownIds, cardSelector = '.card') {
    // Counter system prevents z-index conflicts
    // Centralized event handling for consistency
    // Professional styling integration
}
```

### Templates Enhanced
1. **`transactions_list.html`** ⭐ - Transaction Type, Vessel + Product search
2. **`supply_entry.html`** - Vessel selection dropdown  
3. **`transfer_entry.html`** - From/To vessel dropdowns
4. **`waste_entry.html`** - Vessel selection dropdown
5. **`inventory_check.html`** - Stock level dropdown + JS error fixes
6. **`monthly_report.html`** - Month/Year selection dropdowns
7. **`trip_reports.html`** - Vessel/Status filter dropdowns
8. **`po_reports.html`** - Vessel/Status filter dropdowns

### Key Problems Solved
- ✅ **"BOSS Issue"** - Dropdown switching z-index conflicts resolved
- ✅ **Z-Index Stacking** - Professional layer management implemented
- ✅ **Code Duplication** - 40+ lines reduced to 2-4 lines per template
- ✅ **JavaScript Errors** - Null reference issues fixed in inventory_check.js

## Development Environment

### Technology Stack
```python
# Core Framework
Django==5.2.1              # Web framework
python-dotenv==1.1.1        # Environment management

# Database & Performance  
psycopg2-binary==2.9.10     # PostgreSQL support (production)
django-debug-toolbar==5.2.0 # Development debugging

# Document Generation
WeasyPrint==65.1            # PDF generation
openpyxl==3.1.5            # Excel exports
reportlab==4.4.1           # Advanced reporting

# Data Processing
numpy==2.3.0               # Mathematical operations
matplotlib==3.10.3         # Charting capabilities
```

### Database Configuration
- **Development**: SQLite with performance optimizations
- **Production**: PostgreSQL with advanced indexing
- **Integrity**: Database constraints + FIFO validation layer
- **Migrations**: 16 migrations with integrity fixes applied

### Key Development Patterns
```python
# FIFO Operations - Atomic with database locking
with transaction.atomic():
    # Create/consume inventory lots
    # Update transaction records
    # Maintain data integrity

# Cache Management - Versioned for consistency
cache_key = f"{model}_{version}_{id}"
ProductCacheHelper.invalidate_product_cache(product_id)

# Error Handling - Structured approach
InventoryErrorHelper.handle_insufficient_stock(
    vessel=vessel, product=product, required=quantity
)
```

## Configuration & Deployment

### Environment Variables
```bash
# Security
DJANGO_SECRET_KEY           # Production secret key
DJANGO_DEBUG               # Debug mode toggle

# Database  
DATABASE_URL               # Production database connection
DB_NAME, DB_USER, DB_PASSWORD, DB_HOST, DB_PORT

# Email & Notifications
EMAIL_HOST, EMAIL_PORT, EMAIL_USE_TLS
EMAIL_HOST_USER, EMAIL_HOST_PASSWORD
```

### Key Features
- **Multilingual Support**: English/Arabic with RTL layout support
- **Dynamic Pricing**: Vessel-specific pricing for touristic operations  
- **Role-Based Security**: 6 user groups with granular permissions
- **Advanced Reporting**: Comprehensive analytics and export capabilities
- **Real-time Updates**: Cache invalidation and live data synchronization

### Security Features
- **Environment-based Configuration**: Sensitive data in .env files
- **CSRF Protection**: Django's built-in CSRF middleware
- **SQL Injection Prevention**: ORM-based database interactions
- **User Authentication**: Django's authentication framework
- **Permission Management**: Role-based access control

## Recent Achievements ✅

### Major Implementation (August 19, 2025) ⭐ LATEST
- **Transfer Workflow System**: Complete collaborative two-party approval system with real-time notifications
- **User-Vessel Assignment System**: Enterprise-grade vessel-based access control and permissions  
- **Critical Bug Fixes**: Comprehensive resolution of transfer management and transaction deletion issues
- **Enhanced Security**: CSRF token fixes, permission system corrections, and bidirectional deletion safety
- **Professional UI/UX**: Real-time dashboard, workflow interfaces, and enhanced user experience

### Previous Major Features (August 2025)
- **Unified Dropdown System**: Professional UI upgrade across entire system
- **Database Integrity**: Advanced constraint system with validation commands
- **Performance Optimization**: Strategic indexing and query optimization  
- **Code Quality**: Centralized utility framework and helper modules
- **Documentation**: Comprehensive system documentation and guides

### Latest System Statistics
- **85+ Files Modified**: Major system enhancement with workflow and access control systems
- **6,460+ Lines Added**: Enterprise-grade collaborative features and critical fixes
- **20+ New Files Created**: Complete vessel_management app with workflow infrastructure
- **25+ Database Constraints**: Advanced data integrity with workflow and security validation
- **12+ Management Commands**: Administrative automation and user assignment tools
- **10+ New Views**: Complete transfer workflow and user management system
- **5 New Templates**: Professional transfer workflow interface components

## Development Guidelines

### Code Standards
```python
# Imports Organization
from django.db import models              # Django core
from decimal import Decimal              # Python standard
from vessels.models import Vessel        # Local apps
from frontend.utils.cache_helpers import # Utilities
```

### Best Practices
- **Atomic Operations**: Use database transactions for inventory changes
- **Cache Management**: Implement versioned caching strategies  
- **Error Handling**: Use structured error helpers for consistency
- **Testing**: Comprehensive test coverage for inventory operations
- **Documentation**: Maintain inline documentation for complex logic

### UI/UX Standards
- **Bootstrap Integration**: Use established dropdown patterns
- **Responsive Design**: Mobile-first approach with accessibility
- **Performance**: Optimize asset loading and minimize JavaScript
- **Consistency**: Follow universal dropdown system patterns
- **Accessibility**: ARIA labels and keyboard navigation support

---

## Quick Reference Commands

```bash
# Development Server
python manage.py runserver

# Database Operations  
python manage.py migrate
python manage.py rebuild_inventory_lots
python manage.py check_db_integrity --verbose --fix

# Authentication Setup
python manage.py activate_auth

# Data Validation
python manage.py reconcile_inventory
python manage.py verify_inventory_rebuild

# Cache Management
python manage.py monitor_cache
```

---

*Project Status: Production-Ready with Enterprise-Grade Features*  
*Last Updated: August 19, 2025*  
*Latest Major Features: ✅ Transfer Workflow System + User-Vessel Access Control + Critical Bug Fixes*

- CRITICAL: Always keep CLAUDE.md and todos.md file under 40,000 characters
- Always update todos.md with the plans and then always update it with the in-progress and then always update it with completed plans/phases/points
- CRITICAL: Never use import inside functions or classes, always use them at the top of the file unless it might cause a circular reference.
- CRITICAL: Never use EMOJIS in ANY management commands (api\management, frontend\management\commands, or any Django management commands) as they cause UnicodeEncodeError on Windows systems. Always use plain text alternatives.
- CRITICAL: Replace emojis with plain text in all log messages.
- Before running "python manage.py runserver", always make sure that all instances of runserver are killed.
- Always update @todos.md after finishing any point or phase.
- After implementing any phase or anything, always run a test.