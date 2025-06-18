#!/usr/bin/env python3
"""
Analysis script to explore employee-related data available in Toast Orders API.
This script will examine order data to identify any employee/labor-related fields.
"""

import os
import sys
import json
import datetime
from toast_client import ToastAPIClient

def analyze_order_structure(order_data):
    """Analyze order structure for employee-related fields."""
    employee_fields = []
    labor_fields = []
    tip_fields = []
    
    def find_employee_fields(obj, path=""):
        """Recursively search for employee-related fields."""
        if isinstance(obj, dict):
            for key, value in obj.items():
                current_path = f"{path}.{key}" if path else key
                
                # Check for employee-related keywords
                if any(keyword in key.lower() for keyword in ['employee', 'server', 'staff', 'user', 'worker']):
                    employee_fields.append({
                        'path': current_path,
                        'key': key,
                        'value_type': type(value).__name__,
                        'sample_value': str(value)[:100] if value else None
                    })
                
                # Check for labor-related keywords
                if any(keyword in key.lower() for keyword in ['job', 'role', 'shift', 'labor', 'hour', 'time']):
                    labor_fields.append({
                        'path': current_path,
                        'key': key,
                        'value_type': type(value).__name__,
                        'sample_value': str(value)[:100] if value else None
                    })
                
                # Check for tip/gratuity-related keywords
                if any(keyword in key.lower() for keyword in ['tip', 'gratuity', 'service']):
                    tip_fields.append({
                        'path': current_path,
                        'key': key,
                        'value_type': type(value).__name__,
                        'sample_value': str(value)[:100] if value else None
                    })
                
                # Recurse into nested objects
                find_employee_fields(value, current_path)
        
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                find_employee_fields(item, f"{path}[{i}]")
    
    find_employee_fields(order_data)
    
    return {
        'employee_fields': employee_fields,
        'labor_fields': labor_fields,
        'tip_fields': tip_fields
    }

def test_labor_api_access(client):
    """Test if we can access the Labor API endpoints."""
    print("\n" + "="*60)
    print("TESTING LABOR API ACCESS")
    print("="*60)
    
    try:
        # Try to access the employees endpoint
        print("Attempting to access /labor/v1/employees...")
        result = client._make_request("/labor/v1/employees", params={'page': '1', 'pageSize': '5'})
        print(f"SUCCESS: Employees endpoint accessible")
        print(f"Response keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
        if isinstance(result, dict) and result:
            print(f"Sample data structure: {json.dumps(result, indent=2)[:500]}...")
        return True
    except Exception as e:
        print(f"Failed to access employees endpoint: {e}")
    
    try:
        # Try to access the jobs endpoint
        print("\nAttempting to access /labor/v1/jobs...")
        result = client._make_request("/labor/v1/jobs")
        print(f"SUCCESS: Jobs endpoint accessible")
        print(f"Response keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
        if isinstance(result, dict) and result:
            print(f"Sample data structure: {json.dumps(result, indent=2)[:500]}...")
        return True
    except Exception as e:
        print(f"Failed to access jobs endpoint: {e}")
    
    try:
        # Try to access the time entries endpoint
        print("\nAttempting to access /labor/v1/timeEntries...")
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        params = {
            'startDate': f"{today}T00:00:00.000Z",
            'endDate': f"{today}T23:59:59.999Z",
            'page': '1',
            'pageSize': '5'
        }
        result = client._make_request("/labor/v1/timeEntries", params=params)
        print(f"SUCCESS: Time entries endpoint accessible")
        print(f"Response keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
        if isinstance(result, dict) and result:
            print(f"Sample data structure: {json.dumps(result, indent=2)[:500]}...")
        return True
    except Exception as e:
        print(f"Failed to access time entries endpoint: {e}")
    
    return False

def main():
    """Main analysis function."""
    print("="*80)
    print("TOAST API EMPLOYEE DATA ANALYSIS")
    print("="*80)
    
    try:
        # Initialize client
        client = ToastAPIClient()
        
        # Test Labor API access first
        labor_api_accessible = test_labor_api_access(client)
        
        # Get sample order data
        print("\n" + "="*60)
        print("ANALYZING ORDER DATA STRUCTURE")
        print("="*60)
        
        # Get yesterday's orders (more likely to have data)
        yesterday = datetime.datetime.now() - datetime.timedelta(days=1)
        date_str = yesterday.strftime("%Y-%m-%d")
        start_date = f"{date_str}T00:00:00.000Z"
        end_date = f"{date_str}T23:59:59.999Z"
        
        print(f"Fetching orders for {date_str}...")
        orders_response = client.get_orders(start_date, end_date)
        
        if isinstance(orders_response, dict) and 'orders' in orders_response:
            orders = orders_response['orders']
        elif isinstance(orders_response, list):
            orders = orders_response
        else:
            orders = []
        
        print(f"Retrieved {len(orders)} orders")
        
        if orders:
            print("\nAnalyzing first order for employee-related fields...")
            analysis = analyze_order_structure(orders[0])
            
            print(f"\nEmployee-related fields found: {len(analysis['employee_fields'])}")
            for field in analysis['employee_fields']:
                print(f"  - {field['path']}: {field['value_type']} = {field['sample_value']}")
            
            print(f"\nLabor-related fields found: {len(analysis['labor_fields'])}")
            for field in analysis['labor_fields']:
                print(f"  - {field['path']}: {field['value_type']} = {field['sample_value']}")
            
            print(f"\nTip/gratuity-related fields found: {len(analysis['tip_fields'])}")
            for field in analysis['tip_fields']:
                print(f"  - {field['path']}: {field['value_type']} = {field['sample_value']}")
            
            # Save sample order for manual inspection
            sample_file = f"sample_order_{date_str}.json"
            with open(sample_file, 'w') as f:
                json.dump(orders[0], f, indent=2)
            print(f"\nSample order saved to: {sample_file}")
        else:
            print("No orders found for analysis")
        
        # Summary
        print("\n" + "="*60)
        print("ANALYSIS SUMMARY")
        print("="*60)
        print(f"Labor API Access: {'✓ Available' if labor_api_accessible else '✗ Not Available'}")
        print(f"Orders API Access: ✓ Available")
        print(f"Sample Orders Retrieved: {len(orders)}")
        
        if orders:
            analysis = analyze_order_structure(orders[0])
            print(f"Employee fields in orders: {len(analysis['employee_fields'])}")
            print(f"Labor fields in orders: {len(analysis['labor_fields'])}")
            print(f"Tip/gratuity fields in orders: {len(analysis['tip_fields'])}")
        
    except Exception as e:
        print(f"Error during analysis: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()