#!/usr/bin/env python3
"""
JavaScript Syntax Validator
Quick check for syntax errors in refactored JavaScript files
"""

import subprocess
import sys
from pathlib import Path

def check_js_syntax(file_path):
    """Check JavaScript syntax using Node.js if available"""
    try:
        # Try using node.js to check syntax
        result = subprocess.run(
            ['node', '-c', str(file_path)], 
            capture_output=True, 
            text=True
        )
        
        if result.returncode == 0:
            return True, "Syntax OK"
        else:
            return False, f"Syntax Error: {result.stderr}"
    
    except FileNotFoundError:
        # Node.js not available, do basic checks
        return basic_js_check(file_path)

def basic_js_check(file_path):
    """Basic JavaScript syntax checks without Node.js"""
    try:
        content = file_path.read_text()
        
        # Basic checks
        issues = []
        
        # Check for unmatched braces
        open_braces = content.count('{')
        close_braces = content.count('}')
        if open_braces != close_braces:
            issues.append(f"Unmatched braces: {open_braces} open, {close_braces} close")
        
        # Check for unmatched parentheses
        open_parens = content.count('(')
        close_parens = content.count(')')
        if open_parens != close_parens:
            issues.append(f"Unmatched parentheses: {open_parens} open, {close_parens} close")
        
        # Check for basic syntax issues
        if 'function(' in content:
            issues.append("Possible missing space: 'function(' should be 'function ('")
        
        if issues:
            return False, f"Potential Issues: {'; '.join(issues)}"
        else:
            return True, "Basic checks passed (install Node.js for full validation)"
    
    except Exception as e:
        return False, f"Error reading file: {e}"

def main():
    js_dir = Path('frontend/static/frontend/js')
    
    # Files to check
    refactored_files = [
        'inventory_check_refactored.js',
        'bulk_pricing_management_refactored.js', 
        'category_management_refactored.js',
        'daily_report_refactored.js'
    ]
    
    # Also check utility files
    utility_files = [
        'utils/PageManager.js',
        'utils/DropdownManager.js',
        'utils/DataTableManager.js'
    ]
    
    print("JavaScript Syntax Validation")
    print("=" * 40)
    
    all_files = refactored_files + utility_files
    passed = 0
    failed = 0
    
    for filename in all_files:
        file_path = js_dir / filename
        
        if file_path.exists():
            success, message = check_js_syntax(file_path)
            print(f"{filename:<40} {message}")
            
            if success:
                passed += 1
            else:
                failed += 1
        else:
            print(f"{filename:<40} File not found")
            failed += 1
    
    print("\n" + "=" * 40)
    print(f"Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("All JavaScript files validated successfully!")
        return 0
    else:
        print("Some files have issues - check before testing")
        return 1

if __name__ == '__main__':
    sys.exit(main())