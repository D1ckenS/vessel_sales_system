import sqlite3
import os

def check_database_indexes():
    """Check what indexes exist in the SQLite database"""
    
    db_path = 'db.sqlite3'
    
    if not os.path.exists(db_path):
        print("❌ Database file not found!")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("🔍 Checking Database Indexes...")
        print("=" * 50)
        
        # Get all indexes
        cursor.execute("""
            SELECT name, tbl_name, sql 
            FROM sqlite_master 
            WHERE type = 'index' 
            AND name NOT LIKE 'sqlite_%'
            ORDER BY tbl_name, name
        """)
        
        indexes = cursor.fetchall()
        
        # Group by table
        tables = {}
        for index_name, table_name, sql in indexes:
            if table_name not in tables:
                tables[table_name] = []
            tables[table_name].append((index_name, sql))
        
        # Display results
        for table_name in sorted(tables.keys()):
            print(f"\n📋 Table: {table_name}")
            print("-" * 30)
            
            for index_name, sql in tables[table_name]:
                print(f"   ✓ {index_name}")
                if sql:
                    # Extract columns from CREATE INDEX statement
                    if 'ON' in sql and '(' in sql:
                        columns_part = sql.split('(', 1)[1].split(')', 1)[0]
                        print(f"     └─ Columns: {columns_part}")
        
        print(f"\n📊 Summary: Found {len(indexes)} custom indexes across {len(tables)} tables")
        
        # Check for our performance indexes specifically
        performance_indexes = [
            'transaction_product_idx',
            'transaction_trip_idx', 
            'inventorylot_vessel_product_idx',
            'inventorylot_fifo_idx',
            'product_category_idx',
            'vesselproductprice_vessel_idx'
        ]
        
        existing_performance_indexes = [idx[0] for idx in indexes if idx[0] in performance_indexes]
        
        print(f"\n🚀 Performance Indexes Applied: {len(existing_performance_indexes)}/{len(performance_indexes)}")
        
        if len(existing_performance_indexes) == len(performance_indexes):
            print("✅ All performance indexes are applied!")
        else:
            missing = set(performance_indexes) - set(existing_performance_indexes)
            print(f"⚠️ Missing indexes: {', '.join(missing)}")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error checking database: {e}")

if __name__ == "__main__":
    check_database_indexes()