#!/usr/bin/env python3
"""
Toast Tips API Script - Tips and Server Sales Analysis

This script retrieves order information from the Toast Orders API and processes it to extract:
1. Total tips for each day in the specified date range
2. Total sales per server (by server.guid)

The script uses the same API infrastructure as get_orders.py with rate limiting protection.
Date determination follows the same approach as get_orders.py - trusts the Toast API's date 
filtering and processes all returned orders without additional filtering.

Prerequisites:
1. Valid Toast API credentials (client ID and client secret) configured in config.py
2. Restaurant GUID configured in config.py
3. Appropriate permissions to access order data in Toast

Usage examples:
- Fetch tips for today: python get_tips.py --output-file tips.json
- Fetch tips for a specific date range: python get_tips.py --dates 2025-05-01 2025-05-10 --output-file tips.json
- Fetch for specific location: python get_tips.py --location-index 4 --dates 2025-05-01 2025-05-10 --output-file tips.json
"""

import os
import sys
import argparse
import json
import datetime
import time
import requests
import logging
import traceback
from typing import Dict, Any, List, Optional
from collections import defaultdict

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "get_tips.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("toast-tips")

# Error webhook URL
ERROR_WEBHOOK_URL = "https://fynch.app.n8n.cloud/webhook/358766dc-09ae-4549-b762-f7079c0ac922"

def send_error_to_webhook(error_msg: str, error_traceback: str, context: str = "get_tips"):
    """Send error details to webhook"""
    try:
        payload = {
            "error": error_msg,
            "traceback": error_traceback,
            "context": context,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "environment": os.environ.get("ENVIRONMENT", "unknown"),
            "location_index": os.environ.get("TOAST_LOCATION_INDEX", "unknown")
        }
        
        logger.info(f"Sending error to webhook: {ERROR_WEBHOOK_URL}")
        response = requests.post(
            ERROR_WEBHOOK_URL,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        logger.info(f"Error sent to webhook. Response: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"Failed to send error to webhook: {str(e)}")
        return False

def send_data_to_webhook(processed_data, webhook_url=None):
    """
    Send processed tips and server data to webhook.
    
    Args:
        processed_data: Processed tips and server data
        webhook_url: Optional webhook URL to override default
    """
    # Default webhook URL if none provided
    if webhook_url is None:
        webhook_url = "https://originaljoes.app.n8n.cloud/webhook/57938ed1-012b-47f7-8adf-3614117ae333"
    
    logger.info(f"Sending tips data to webhook: {webhook_url}")
    
    try:
        # Print data size before sending
        data_size = len(json.dumps(processed_data))
        logger.info(f"Data size: {data_size/1024:.1f}KB")
        
        response = requests.post(
            webhook_url,
            headers={"Content-Type": "application/json"},
            json=processed_data,
            timeout=30
        )
        logger.info(f"Webhook response: {response.status_code} - {response.text[:200]}")  # Only print first 200 chars of response
        response.raise_for_status()
        return True
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        logger.error(f"Webhook error: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        if hasattr(e, 'response') and e.response:
            logger.error(f"Response status: {e.response.status_code}")
            logger.error(f"Response headers: {dict(e.response.headers)}")
        
        # Don't send webhook errors to the error webhook to avoid potential loops
        # Only log them locally
        return False

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Fetch tips and server sales data from Toast API')
    
    # Create a mutually exclusive group for date parameters
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument('--date', help='Specify a single date in YYYY-MM-DD format (default: today)')
    date_group.add_argument('--dates', nargs=2, metavar=('START_DATE', 'END_DATE'), 
                        help='Specify date range in YYYY-MM-DD format (e.g., --dates 2025-01-01 2025-01-07)')
    
    parser.add_argument('--location-index', type=int, choices=range(1, 6),
                       help='Location index (1-5) to determine which restaurant GUID to use')
    parser.add_argument('--output-file', dest='output', help='File to save tips and server data')
    parser.add_argument('--webhook', action='store_true', help='Send processed data to webhook')
    parser.add_argument('--response-webhook-url', dest='response_webhook_url', help='Webhook URL to send the response data to')
    parser.add_argument('--debug', action='store_true', help='Enable detailed debugging output')
    
    args = parser.parse_args()
    
    # Validate that at least one output method is specified
    if not args.output and not args.webhook and not args.response_webhook_url:
        parser.error("Must specify either --output-file, --webhook, or --response-webhook-url (or multiple)")
    
    # Set location index in environment if provided and not already set
    if args.location_index and not os.getenv('TOAST_LOCATION_INDEX'):
        os.environ['TOAST_LOCATION_INDEX'] = str(args.location_index)
        logger.info(f"Setting location index to {args.location_index}")
    
    return args

# Parse arguments and set location index before importing other modules
args = parse_args()

# Try to import ToastAPIClient from toast_client.py
try:
    # Add the project root to the path
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
    from server.toast_client import ToastAPIClient
except ImportError as e:
    logger.error(f"Failed to import ToastAPIClient: {str(e)}")
    error_traceback = traceback.format_exc()
    send_error_to_webhook(
        error_msg=f"Failed to import ToastAPIClient: {str(e)}",
        error_traceback=error_traceback,
        context="import_error"
    )
    raise

def get_employee_mapping():
    """
    Fetch all employees from Toast API and create a mapping from GUID to name.
    
    Returns:
        Dictionary mapping employee GUIDs to names
    """
    try:
        client = ToastAPIClient()
        logger.info("Fetching all employees from Toast API...")
        
        # Fetch all employees (no GUID parameter)
        employees_response = client.get_employee(None)
        
        # Extract employees from response
        if isinstance(employees_response, list):
            employees = employees_response
        elif isinstance(employees_response, dict) and 'employees' in employees_response:
            employees = employees_response['employees']
        else:
            logger.warning("Unexpected employee API response structure")
            return {}
        
        # Create mapping from GUID to employee info (name and externalEmployeeId)
        employee_mapping = {}
        for employee in employees:
            if isinstance(employee, dict) and 'guid' in employee:
                guid = employee['guid']
                first_name = employee.get('firstName', '')
                last_name = employee.get('lastName', '')
                chosen_name = employee.get('chosenName', '')
                external_employee_id = employee.get('externalEmployeeId', '')
                
                # Use chosen name if available, otherwise first + last
                if chosen_name:
                    full_name = chosen_name
                else:
                    full_name = f"{first_name} {last_name}".strip()
                    if not full_name:
                        full_name = f"Employee {guid[-8:]}"
                
                employee_mapping[guid] = {
                    'name': full_name,
                    'externalEmployeeId': external_employee_id
                }
        
        logger.info(f"Successfully mapped {len(employee_mapping)} employees")
        return employee_mapping
        
    except Exception as e:
        logger.error(f"Failed to fetch employees from API: {e}")
        logger.warning("Falling back to server_map.json if available")
        return {}

def get_job_mapping():
    """
    Fetch all jobs from Toast API and create a mapping from GUID to job name.
    
    Returns:
        Dictionary mapping job GUIDs to job names
    """
    try:
        client = ToastAPIClient()
        logger.info("Fetching all jobs from Toast API...")
        
        # Fetch all jobs (no job IDs parameter)
        jobs_response = client.get_jobs(None)
        
        # Extract jobs from response
        if isinstance(jobs_response, list):
            jobs = jobs_response
        elif isinstance(jobs_response, dict) and 'jobs' in jobs_response:
            jobs = jobs_response['jobs']
        else:
            logger.warning("Unexpected jobs API response structure")
            return {}
        
        # Create mapping from GUID to job name
        job_mapping = {}
        for job in jobs:
            if isinstance(job, dict) and 'guid' in job:
                guid = job['guid']
                job_name = job.get('title', job.get('name', f"Job {guid[-8:]}"))
                job_mapping[guid] = job_name
        
        logger.info(f"Successfully mapped {len(job_mapping)} jobs")
        return job_mapping
        
    except Exception as e:
        logger.error(f"Failed to fetch jobs from API: {e}")
        logger.warning("Job names will be displayed as GUIDs")
        return {}

def calculate_unpaid_break_hours(breaks):
    """
    Calculate total unpaid break hours from a list of breaks.
    
    Args:
        breaks: List of break objects with 'paid', 'inDate', and 'outDate' fields
        
    Returns:
        Float representing unpaid break hours with two decimal places
    """
    if not breaks or not isinstance(breaks, list):
        return 0.0
    
    total_unpaid_hours = 0.0
    
    for break_item in breaks:
        # Skip if break is paid or if it's missing required fields
        if break_item.get('paid', False):
            continue
            
        in_date = break_item.get('inDate')
        out_date = break_item.get('outDate')
        
        if not in_date or not out_date:
            continue
            
        try:
            # Parse timestamps
            in_dt = datetime.datetime.fromisoformat(in_date.replace('Z', '+00:00'))
            out_dt = datetime.datetime.fromisoformat(out_date.replace('Z', '+00:00'))
            
            # Calculate duration in hours
            duration = out_dt - in_dt
            hours = duration.total_seconds() / 3600
            
            total_unpaid_hours += hours
            
        except Exception as e:
            logger.warning(f"Error calculating break duration for break {break_item.get('guid', 'unknown')}: {e}")
            continue
    
    return round(total_unpaid_hours, 2)

def fetch_and_process_time_entries(client, date_range, employee_mapping, sales_by_server=None, tips_by_server=None, job_mapping=None, tax_by_server=None, location_index=None):
    """
    Fetch time entries data from Toast API and process it with employee information.
    
    Args:
        client: ToastAPIClient instance
        date_range: Dict with 'start_date' and 'end_date' strings in YYYY-MM-DD format
        employee_mapping: Dictionary mapping employee GUIDs to names
        sales_by_server: Dictionary with sales data by server GUID and date
        tips_by_server: Dictionary with tips data by server GUID and date
        job_mapping: Dictionary mapping job GUIDs to job names
        tax_by_server: Dictionary with tax data by server GUID and date
        location_index: Location index (1-5) to determine which positions to include in sales/tips data
        
    Returns:
        Dictionary with time entries data organized by day and employee
    """
    # First fetch all employees to get job references
    try:
        logger.info("Fetching complete employee data for job references...")
        employees_response = client.get_employee(None)
        
        # Extract employees from response
        if isinstance(employees_response, list):
            employees = employees_response
        elif isinstance(employees_response, dict) and 'employees' in employees_response:
            employees = employees_response['employees']
        else:
            logger.warning("Unexpected employee API response structure")
            employees = []
        
        # Create mapping from employee GUID to job references
        employee_job_mapping = {}
        for employee in employees:
            if isinstance(employee, dict) and 'guid' in employee:
                guid = employee['guid']
                job_references = employee.get('jobReferences', [])
                # Get the first job reference GUID (primary position)
                if job_references and len(job_references) > 0:
                    employee_job_mapping[guid] = job_references[0].get('guid', '')
                else:
                    employee_job_mapping[guid] = ''
        
        logger.info(f"Mapped job references for {len(employee_job_mapping)} employees")
        
    except Exception as e:
        logger.error(f"Failed to fetch employees for job mapping: {e}")
        employee_job_mapping = {}
    try:
        logger.info(f"Fetching time entries for date range: {date_range['start_date']} to {date_range['end_date']}")
        
        # Always use date range format as businessDate parameter causes 404 errors
        start_date = f"{date_range['start_date']}T00:00:00.000Z"
        end_date = f"{date_range['end_date']}T23:59:59.999Z"
        
        # Fetch time entries using date range format
        time_entries_response = client.get_time_entries(
            start_date=start_date,
            end_date=end_date,
            include_archived=True,
            include_missed_breaks=True
        )
        
        # Extract time entries from response
        if isinstance(time_entries_response, dict):
            time_entries_data = time_entries_response.get('timeEntries', time_entries_response.get('data', []))
        elif isinstance(time_entries_response, list):
            time_entries_data = time_entries_response
        else:
            logger.warning("Unexpected time entries response structure")
            time_entries_data = []
        
        logger.info(f"Retrieved {len(time_entries_data)} time entries from Toast API")
        
        # Process time entries by day
        time_entries_by_day = defaultdict(list)
        
        for entry in time_entries_data:
            # Get business date (in YYYYMMDD format)
            business_date = entry.get('businessDate')
            if not business_date:
                continue
                
            # Convert business date to YYYY-MM-DD format
            business_date_str = str(business_date)
            if len(business_date_str) == 8:
                formatted_date = f"{business_date_str[:4]}-{business_date_str[4:6]}-{business_date_str[6:8]}"
            else:
                logger.warning(f"Invalid business date format: {business_date}")
                continue
            
            # Extract employee information
            employee_ref = entry.get('employeeReference', {})
            employee_guid = employee_ref.get('guid')
            
            if not employee_guid:
                logger.warning(f"No employee GUID found for time entry {entry.get('guid')}")
                continue
            
            # Get employee name from mapping
            employee_info = employee_mapping.get(employee_guid, {})
            if isinstance(employee_info, dict):
                employee_name = employee_info.get('name', f"Unknown Employee ({employee_guid[-8:]})")
            else:
                # Fallback for old format
                employee_name = employee_info if employee_info else f"Unknown Employee ({employee_guid[-8:]})"
            
            # Format time entries
            in_date = entry.get('inDate')
            out_date = entry.get('outDate')
            
            # Parse time in and time out
            time_in = ""
            time_out = ""
            if in_date:
                try:
                    in_dt = datetime.datetime.fromisoformat(in_date.replace('Z', '+00:00'))
                    # Convert from UTC to local time (subtract 7 hours for Pacific Time)
                    in_dt_local = in_dt - datetime.timedelta(hours=7)
                    time_in = in_dt_local.strftime('%I:%M%p').lower()
                except:
                    time_in = ""
            if out_date:
                try:
                    out_dt = datetime.datetime.fromisoformat(out_date.replace('Z', '+00:00'))
                    # Convert from UTC to local time (subtract 7 hours for Pacific Time)
                    out_dt_local = out_dt - datetime.timedelta(hours=7)
                    time_out = out_dt_local.strftime('%I:%M%p').lower()
                except:
                    time_out = ""
            
            # Calculate hours including unpaid break hours from breaks data
            regular_hours = entry.get('regularHours', 0.0)
            overtime_hours = entry.get('overtimeHours', 0.0)

            # Calculate payable hours (total hours minus unpaid break hours)
            payable_hours = regular_hours + overtime_hours
            
            # Calculate unpaid break hours from breaks data
            breaks = entry.get('breaks', [])
            unpaid_break_hours = calculate_unpaid_break_hours(breaks)

            total_hours = payable_hours + unpaid_break_hours
            
            # Extract declared cash tips
            declared_cash_tips_raw = entry.get('declaredCashTips', 0.0)
            declared_cash_tips = float(declared_cash_tips_raw) if declared_cash_tips_raw is not None else 0.0
            
            # Get job reference for position from the time entry itself
            job_ref = entry.get('jobReference', {})
            position_guid = job_ref.get('guid', '')
            
            # Fallback to employee job mapping if time entry doesn't have job reference
            if not position_guid:
                position_guid = employee_job_mapping.get(employee_guid, '')
            
            # Convert position GUID to job name if job mapping is available
            if job_mapping and position_guid in job_mapping:
                position_name = job_mapping[position_guid]
            else:
                position_name = position_guid if position_guid else 'Unknown Position'
            
            # Check if this employee should have sales, tips, and tax data populated
            server_job_guid = "9d5d64b3-8d59-4aae-b340-02dd970b54dd"
            cashier_position_guid = "6c0920e7-c285-4fbd-b7df-5cb910737ff1"  # Cashier1
            loj_expo_position_guid = "6339f37d-0039-433f-aee7-6ee33d2cd40a"  # LOJ Expo
            
            sales = 0.0
            non_cash_tips = 0.0
            tax_amount = 0.0
            
            # Determine if we should include this position based on location index
            include_position = False
            if position_guid == server_job_guid:
                # Always include servers
                include_position = True
            elif location_index == 2 and position_guid in [cashier_position_guid, loj_expo_position_guid]:
                # Include cashiers and LOJ expo for location index 2
                include_position = True
            
            if include_position:
                # Look for sales data for this employee on this date
                if sales_by_server and formatted_date in sales_by_server and employee_guid in sales_by_server[formatted_date]:
                    sales = sales_by_server[formatted_date][employee_guid]
                
                # Look for tips data for this employee on this date
                if tips_by_server and formatted_date in tips_by_server and employee_guid in tips_by_server[formatted_date]:
                    non_cash_tips = tips_by_server[formatted_date][employee_guid]
                
                # Look for tax data for this employee on this date
                if tax_by_server and formatted_date in tax_by_server and employee_guid in tax_by_server[formatted_date]:
                    tax_amount = tax_by_server[formatted_date][employee_guid]
            
            # Create time entry record with new format
            time_entry_record = {
                'employeeGuid': employee_guid,
                'employeeName': employee_name,
                'businessDate': datetime.datetime.strptime(formatted_date, '%Y-%m-%d').strftime('%m/%d/%Y'),
                'timeIn': time_in,
                'timeOut': time_out,
                'totalHours': round(total_hours, 2),
                'unpaidBreakHours': round(unpaid_break_hours, 2),
                'payableHours': round(payable_hours, 2),
                'position': position_name,
                'positionGuid': position_guid,  # Keep the GUID for reference
                'sales': round(sales, 2),
                'nonCashTips': round(non_cash_tips, 2),
                'totalGratuity': 0.0,
                'cashTipsDeclared': round(declared_cash_tips, 2),
                'taxAmount': round(tax_amount, 2),
                'timeEntryGuid': entry.get('guid')
            }
            
            time_entries_by_day[formatted_date].append(time_entry_record)
        
        # Sort entries within each day by employee name
        for date in time_entries_by_day:
            time_entries_by_day[date].sort(key=lambda x: x['employeeName'])
        
        # Convert to regular dict and sort by date
        time_entries_by_day_sorted = dict(sorted(time_entries_by_day.items()))
        
        logger.info(f"Processed time entries for {len(time_entries_by_day_sorted)} days")
        
        # Calculate summary statistics from processed data
        total_hours = 0.0
        total_payable_hours = 0.0
        total_unpaid_break_hours = 0.0
        
        for day_entries in time_entries_by_day_sorted.values():
            for entry in day_entries:
                total_hours += entry.get('totalHours', 0.0)
                total_payable_hours += entry.get('payableHours', 0.0)
                total_unpaid_break_hours += entry.get('unpaidBreakHours', 0.0)
        
        return {
            'timeEntriesByDay': time_entries_by_day_sorted,
            'summary': {
                'totalTimeEntries': len(time_entries_data),
                'daysWithTimeEntries': len(time_entries_by_day_sorted),
                'totalHours': round(total_hours, 2),
                'totalPayableHours': round(total_payable_hours, 2),
                'totalUnpaidBreakHours': round(total_unpaid_break_hours, 2),
                # Keep old fields for backward compatibility
                'totalRegularHours': sum(entry.get('regularHours', 0.0) for entry in time_entries_data),
                'totalOvertimeHours': sum(entry.get('overtimeHours', 0.0) for entry in time_entries_data)
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching time entries: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            'timeEntriesByDay': {},
            'summary': {
                'totalTimeEntries': 0,
                'daysWithTimeEntries': 0,
                'totalHours': 0.0,
                'totalPayableHours': 0.0,
                'totalUnpaidBreakHours': 0.0,
                'totalRegularHours': 0.0,
                'totalOvertimeHours': 0.0
            },
            'error': str(e)
        }

def process_tips_data(orders_data, location_index=None, date_range=None):
    """
    Process orders data to extract tips per day and sales per server.
    Also fetch and process time entries data for the same date range.
    
    Uses the same date determination approach as get_orders - trusts the Toast API's 
    date filtering and processes all returned orders without additional filtering.
    Extracts dates from order data only for grouping purposes.
    
    Args:
        orders_data: Raw orders data from Toast API (pre-filtered by API date range)
        location_index: Location index (1-5) to determine which restaurant to use
        date_range: Dict with 'start_date' and 'end_date' strings in YYYY-MM-DD format (used for time entries only)
        
    Returns:
        Dictionary with tips per day, sales per server, and time entries data
    """
    # Get location index from environment if not provided
    if location_index is None:
        try:
            location_index = int(os.getenv('TOAST_LOCATION_INDEX', '4'))
            logger.info(f"Using location index from environment: {location_index}")
        except ValueError:
            location_index = 4
            logger.warning(f"Invalid TOAST_LOCATION_INDEX in environment, defaulting to {location_index}")
    else:
        logger.info(f"Using provided location index: {location_index}")
    
    # First try to get employee mapping from API
    server_guid_to_name = get_employee_mapping()
    
    # Get job mapping from API
    job_guid_to_name = get_job_mapping()
    
    # If API failed, fall back to server_map.json
    if not server_guid_to_name:
        try:
            server_map_path = os.path.join(os.path.dirname(__file__), 'server_map.json')
            with open(server_map_path, 'r') as f:
                server_map = json.load(f)
                # Extract servers mapping from oj_wl location
                if 'oj_wl' in server_map and 'servers' in server_map['oj_wl']:
                    server_guid_to_name = server_map['oj_wl']['servers']
                    logger.info(f"Loaded {len(server_guid_to_name)} server mappings from server_map.json")
                else:
                    logger.warning("No server mappings found in server_map.json under oj_wl.servers")
        except FileNotFoundError:
            logger.warning("server_map.json not found, using default server names")
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing server_map.json: {e}")
        except Exception as e:
            logger.error(f"Unexpected error loading server_map.json: {e}")
    
    # Initialize data structures
    tips_by_date = defaultdict(float)
    sales_by_server_by_date = defaultdict(lambda: defaultdict(float))  # {date: {server_guid: amount}}
    tips_by_server_by_date = defaultdict(lambda: defaultdict(float))   # {date: {server_guid: amount}}
    tax_by_server_by_date = defaultdict(lambda: defaultdict(float))    # {date: {server_guid: amount}}
    
    # Track processing statistics
    total_orders_processed = 0
    total_payments_processed = 0
    orders_with_tips = 0
    
    logger.info(f"Processing {len(orders_data)} orders for tips and server sales...")
    
    # Loop through all orders
    for order in orders_data:
        total_orders_processed += 1
        order_has_tips = False
        
        # Extract date for grouping purposes - trust API date filtering like get_orders does
        # Use the same robust date extraction as before, but only for grouping (not filtering)
        order_date = None
        
        # First, try to get the business date from payments (most reliable for business reporting)
        for check in order.get('checks', []):
            for payment in check.get('payments', []):
                if payment.get('paidBusinessDate'):
                    # paidBusinessDate is in format YYYYMMDD, convert to YYYY-MM-DD
                    business_date_str = str(payment['paidBusinessDate'])
                    if len(business_date_str) == 8:
                        order_date = f"{business_date_str[:4]}-{business_date_str[4:6]}-{business_date_str[6:8]}"
                        break
            if order_date:
                break
        
        # Fall back to paidDate or openedDate if no business date found
        if not order_date:
            if order.get('paidDate'):
                order_date = datetime.datetime.fromisoformat(order['paidDate'].replace('Z', '+00:00')).strftime('%Y-%m-%d')
            elif order.get('openedDate'):
                order_date = datetime.datetime.fromisoformat(order['openedDate'].replace('Z', '+00:00')).strftime('%Y-%m-%d')
        
        if not order_date:
            logger.warning(f"Could not determine date for order {order.get('guid', 'unknown')}")
            continue
        
        # Process each check in the order
        for check in order.get('checks', []):
            # Calculate check-level tax using: Total Amount - Check Amount - Tips
            check_amount = float(check.get('amount', 0))
            check_total_amount = float(check.get('totalAmount', 0))
            
            # Calculate total tips for this check
            check_tip_amount = 0.0
            check_server_guid = None
            
            # Process each payment in the check
            for payment in check.get('payments', []):
                total_payments_processed += 1
                
                # Skip voided payments
                if payment.get('voidInfo') is not None:
                    continue
                
                # Extract tip amount and server info
                tip_amount = float(payment.get('tipAmount', 0))
                server_info = payment.get('server')
                server_guid = server_info.get('guid') if server_info else None
                
                # For location index 2, also check for cashier/expo in other payment fields
                # (This may need adjustment based on actual Toast payment data structure)
                employee_guid = server_guid  # Default to server GUID
                
                # Keep track of check totals
                check_tip_amount += tip_amount
                if employee_guid and not check_server_guid:
                    check_server_guid = employee_guid
                
                if tip_amount > 0:
                    tips_by_date[order_date] += tip_amount
                    order_has_tips = True
                    
                    # Track tips by employee and date if employee info is available
                    if employee_guid:
                        tips_by_server_by_date[order_date][employee_guid] += tip_amount
                
                # Extract sales amount and track by employee and date
                payment_amount = float(payment.get('amount', 0))
                
                if employee_guid and payment_amount > 0:
                    sales_by_server_by_date[order_date][employee_guid] += payment_amount
            
            # Calculate check-level tax amount using correct method
            check_tax_amount = check_total_amount - check_amount - check_tip_amount
            
            # Assign tax to the server who handled this check
            if check_server_guid and check_tax_amount > 0:
                tax_by_server_by_date[order_date][check_server_guid] += check_tax_amount
        
        if order_has_tips:
            orders_with_tips += 1
    
    # Convert defaultdicts to regular dicts and sort
    tips_by_date_sorted = dict(sorted(tips_by_date.items()))
    
    # Create server summary with daily records for each server
    server_summary = []
    
    # Get all dates from the data
    all_dates = set(sales_by_server_by_date.keys()) | set(tips_by_server_by_date.keys())
    
    for date in sorted(all_dates):
        # Get all server GUIDs for this date
        servers_with_sales = set(sales_by_server_by_date.get(date, {}).keys())
        servers_with_tips = set(tips_by_server_by_date.get(date, {}).keys())
        all_server_guids_for_date = servers_with_sales | servers_with_tips
        
        for server_guid in sorted(all_server_guids_for_date):
            total_sales = sales_by_server_by_date.get(date, {}).get(server_guid, 0.0)
            total_tips = tips_by_server_by_date.get(date, {}).get(server_guid, 0.0)
            
            # Handle both old string format and new dict format for backward compatibility
            if isinstance(server_guid_to_name.get(server_guid), dict):
                server_info = server_guid_to_name[server_guid]
                server_name = server_info['name']
                external_employee_id = server_info['externalEmployeeId']
            else:
                # Fallback for old format or server_map.json
                server_name = server_guid_to_name.get(server_guid, f"Unknown Server ({server_guid[-8:]})")
                external_employee_id = ""
            
            server_summary.append({
                'date': date,
                'server_guid': server_guid,
                'server_name': server_name,
                'external_employee_id': external_employee_id,
                'total_sales': round(total_sales, 2),
                'total_tips': round(total_tips, 2)
            })
    
    # Calculate summary statistics
    total_tips = sum(tips_by_date.values())
    total_server_sales = sum(
        sum(servers.values()) for servers in sales_by_server_by_date.values()
    )
    
    # Prepare result
    result = {
        'tips_by_date': {date: round(amount, 2) for date, amount in tips_by_date_sorted.items()},
        'sales_by_server': server_summary,
        'summary': {
            'total_tips': round(total_tips, 2),
            'total_server_sales': round(total_server_sales, 2),
            'date_range': {
                'start_date': min(tips_by_date_sorted.keys()) if tips_by_date_sorted else None,
                'end_date': max(tips_by_date_sorted.keys()) if tips_by_date_sorted else None
            },
            'processing_stats': {
                'total_orders_processed': total_orders_processed,
                'total_payments_processed': total_payments_processed,
                'orders_with_tips': orders_with_tips,
                'unique_servers': len(set(record['server_guid'] for record in server_summary)),
                'days_with_tips': len(tips_by_date_sorted),
                'server_day_records': len(server_summary)
            }
        },
        'location_index': location_index
    }
    
    # Fetch and process time entries data if date_range is provided
    time_entries_data = {}
    if date_range:
        try:
            # Initialize client for time entries
            client = ToastAPIClient()
            time_entries_data = fetch_and_process_time_entries(client, date_range, server_guid_to_name, sales_by_server_by_date, tips_by_server_by_date, job_guid_to_name, tax_by_server_by_date, location_index)
            
            # Add time entries data to result
            result['timeEntries'] = time_entries_data
            
            logger.info(f"Fetched {time_entries_data['summary']['totalTimeEntries']} time entries for {time_entries_data['summary']['daysWithTimeEntries']} days")
            logger.info(f"Total hours: {time_entries_data['summary'].get('totalHours', 0.0):.2f}")
            logger.info(f"Total payable hours: {time_entries_data['summary'].get('totalPayableHours', 0.0):.2f}")
            if 'totalRegularHours' in time_entries_data['summary']:
                logger.info(f"Legacy - Regular hours: {time_entries_data['summary']['totalRegularHours']:.2f}")
                logger.info(f"Legacy - Overtime hours: {time_entries_data['summary']['totalOvertimeHours']:.2f}")
            
        except Exception as e:
            logger.error(f"Error processing time entries: {e}")
            result['timeEntries'] = {
                'timeEntriesByDay': {},
                'summary': {
                    'totalTimeEntries': 0,
                    'daysWithTimeEntries': 0,
                    'totalHours': 0.0,
                    'totalPayableHours': 0.0,
                    'totalUnpaidBreakHours': 0.0,
                    'totalRegularHours': 0.0,
                    'totalOvertimeHours': 0.0
                },
                'error': str(e)
            }
    
    # Log processing results
    # Calculate total tax from our new method
    total_server_taxes = sum(
        sum(servers.values()) for servers in tax_by_server_by_date.values()
    )
    
    logger.info(f"Processed {total_orders_processed} orders and {total_payments_processed} payments")
    logger.info(f"Found tips in {orders_with_tips} orders across {len(tips_by_date_sorted)} days")
    logger.info(f"Total tips: ${total_tips:.2f}")
    unique_servers = len(set(record['server_guid'] for record in server_summary))
    logger.info(f"Found sales data for {unique_servers} unique servers across {len(server_summary)} server-day records")
    logger.info(f"Total server sales: ${total_server_sales:.2f}")
    logger.info(f"Total server taxes (check-level calculation): ${total_server_taxes:.2f}")
    
    return result

def main():
    """Main function to run the script"""
    args = parse_args()
    
    logger.info("=" * 80)
    logger.info(f"Toast Tips API Script - Started at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)
    
    try:
        # Get location index from environment if set via command line
        location_index = None
        if 'TOAST_LOCATION_INDEX' in os.environ:
            try:
                location_index = int(os.environ['TOAST_LOCATION_INDEX'])
                logger.info(f"Using location index from environment: {location_index}")
            except ValueError:
                logger.warning("Invalid TOAST_LOCATION_INDEX in environment, defaulting to location index 4")
                location_index = 4
                os.environ['TOAST_LOCATION_INDEX'] = str(location_index)
        
        # If location_index is still None, default to 4
        if location_index is None:
            logger.info("No location index specified, defaulting to location index 4")
            location_index = 4
            os.environ['TOAST_LOCATION_INDEX'] = str(location_index)
        
        # Force reload of config.py to get new GUID based on environment variable
        if location_index is not None:
            # Set environment variable to ensure config.py picks it up
            os.environ['TOAST_LOCATION_INDEX'] = str(location_index)
            logger.info(f"Explicitly setting TOAST_LOCATION_INDEX to {location_index} before client initialization")
            
            # Force unload of config module if it's already been imported
            import sys
            if 'config' in sys.modules:
                logger.info("Removing config module from sys.modules to force fresh import")
                del sys.modules['config']
        
        # Initialize the client - this will now use the updated config
        logger.info("Initializing Toast API client...")
        client = ToastAPIClient()
        
        # Double-check which restaurant GUID is being used
        try:
            import config.config as config
            logger.info(f"Config module imported, TOAST_RESTAURANT_GUID: {config.TOAST_RESTAURANT_GUID}")
            logger.info(f"Config module LOCATION_GUID_MAP: {config.LOCATION_GUID_MAP}")
            used_guid = config.TOAST_RESTAURANT_GUID
            mapped_guid = config.LOCATION_GUID_MAP.get(location_index) if location_index else None
            logger.info(f"Using restaurant GUID: {used_guid} for location index {location_index}")
            if mapped_guid:
                if mapped_guid == used_guid:
                    logger.info(f"Confirmed using correct GUID for location {location_index}")
                else:
                    logger.warning(f"WARNING: Expected to use GUID {mapped_guid} for location {location_index}, but using {used_guid} instead")
        except ImportError:
            logger.warning("Could not import config to verify restaurant GUID")
        
        # Store date information
        date_info = {}
        
        # Handle date parameters
        if args.dates:
            # Date range provided
            start_date_str, end_date_str = args.dates
            start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d")
            end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d")
            
            # Generate list of dates
            date_list = []
            current_date = start_date
            while current_date <= end_date:
                date_list.append(current_date.strftime("%Y-%m-%d"))
                current_date += datetime.timedelta(days=1)
            
            logger.info(f"Processing orders from {start_date_str} to {end_date_str}...")
            logger.info(f"Will process {len(date_list)} days individually...")
            
            # Initialize empty data structures for aggregation
            all_orders = []
            
            # Process each day individually
            for date_str in date_list:
                logger.info(f"\nProcessing {date_str}...")
                
                # Format dates for API
                day_start = f"{date_str}T00:00:00.000Z"
                day_end = f"{date_str}T23:59:59.999Z"
                
                # Fetch orders data for this day
                orders_response = client.get_orders(day_start, day_end)
                
                # Extract orders from response
                if isinstance(orders_response, dict) and 'orders' in orders_response:
                    day_orders = orders_response.get('orders', [])
                elif isinstance(orders_response, list):
                    day_orders = orders_response
                else:
                    logger.warning(f"Unexpected response structure for {date_str}. Keys: {list(orders_response.keys()) if isinstance(orders_response, dict) else 'Not a dict'}")
                    day_orders = []
                
                all_orders.extend(day_orders)
                logger.info(f"Retrieved {len(day_orders)} orders for {date_str}")
            
            # Store date info
            date_info = {
                "startDate": start_date_str,
                "endDate": end_date_str,
                "isDateRange": True
            }
            
            # Process all orders together
            orders_data = all_orders
            
        else:
            # Single date (or default to today)
            if args.date:
                date_str = args.date
            else:
                date_str = datetime.datetime.now().strftime("%Y-%m-%d")
                
            # Format dates for API
            start_date = f"{date_str}T00:00:00.000Z"
            end_date = f"{date_str}T23:59:59.999Z"
            logger.info(f"Fetching orders for {date_str}...")
            
            # Store date info
            date_info = {
                "startDate": date_str,
                "endDate": date_str,
                "isDateRange": False
            }
            
            # Fetch orders data
            orders_response = client.get_orders(start_date, end_date)
            
            # Extract orders from response
            if isinstance(orders_response, dict) and 'orders' in orders_response:
                orders_data = orders_response.get('orders', [])
            elif isinstance(orders_response, list):
                orders_data = orders_response
            else:
                logger.warning(f"Unexpected response structure. Keys: {list(orders_response.keys()) if isinstance(orders_response, dict) else 'Not a dict'}")
                orders_data = []
            
            logger.info(f"Retrieved {len(orders_data)} orders from Toast API")
        
        # Create date range for filtering
        date_range_filter = {
            'start_date': date_info['startDate'],
            'end_date': date_info['endDate']
        }
        
        # Process the data for tips and server sales
        processed_data = process_tips_data(orders_data, location_index, date_range_filter)
        
        # Add date information to processed data
        processed_data['dateInfo'] = date_info
        
        # Display results
        logger.info("\n" + "=" * 80)
        logger.info("TIPS BY DATE")
        logger.info("=" * 80)
        
        for date, tip_amount in processed_data['tips_by_date'].items():
            logger.info(f"{date}: ${tip_amount:.2f}")
        
        logger.info(f"\nTotal Tips: ${processed_data['summary']['total_tips']:.2f}")
        
        logger.info("\n" + "=" * 80)
        logger.info("SALES BY SERVER (DAILY)")
        logger.info("=" * 80)
        
        current_date = None
        for server in processed_data['sales_by_server']:
            # Print date header when we encounter a new date
            if server['date'] != current_date:
                current_date = server['date']
                logger.info(f"\n{current_date}:")
            
            external_id_info = f" [ID: {server['external_employee_id']}]" if server['external_employee_id'] else ""
            logger.info(f"  {server['server_name']} ({server['server_guid'][-8:]}){external_id_info}: Sales: ${server['total_sales']:.2f}, Tips: ${server['total_tips']:.2f}")
        
        logger.info(f"\nTotal Server Sales: ${processed_data['summary']['total_server_sales']:.2f}")
        logger.info(f"Total Server-Day Records: {processed_data['summary']['processing_stats']['server_day_records']}")
        
        # Display time entries information if available
        if 'timeEntries' in processed_data and processed_data['timeEntries']['summary']['totalTimeEntries'] > 0:
            logger.info("\n" + "=" * 80)
            logger.info("TIME ENTRIES BY DATE")
            logger.info("=" * 80)
            
            time_entries_summary = processed_data['timeEntries']['summary']
            logger.info(f"Total Time Entries: {time_entries_summary['totalTimeEntries']}")
            logger.info(f"Total Hours: {time_entries_summary.get('totalHours', 0.0):.2f}")
            logger.info(f"Total Payable Hours: {time_entries_summary.get('totalPayableHours', 0.0):.2f}")
            logger.info(f"Total Unpaid Break Hours: {time_entries_summary.get('totalUnpaidBreakHours', 0.0):.2f}")
            logger.info(f"Days with Time Entries: {time_entries_summary['daysWithTimeEntries']}")
            # Show legacy fields if available
            if 'totalRegularHours' in time_entries_summary:
                logger.info(f"Legacy - Regular Hours: {time_entries_summary['totalRegularHours']:.2f}")
                logger.info(f"Legacy - Overtime Hours: {time_entries_summary['totalOvertimeHours']:.2f}")
            
            # Display time entries by day
            for date, entries in processed_data['timeEntries']['timeEntriesByDay'].items():
                logger.info(f"\n{date}:")
                day_total_hours = 0.0
                for entry in entries:
                    time_in = entry.get('timeIn', 'N/A')
                    time_out = entry.get('timeOut', 'N/A')
                    total_hours = entry.get('totalHours', 0.0)
                    sales = entry.get('sales', 0.0)
                    position = entry.get('position', 'Unknown Position')
                    day_total_hours += total_hours
                    sales_info = f" Sales: ${sales:.2f}" if sales > 0 else ""
                    logger.info(f"  {entry['employeeName']}: {time_in}-{time_out} ({total_hours:.2f}h) Pos: {position}{sales_info}")
                logger.info(f"  Day Total: {day_total_hours:.2f} hours")
        elif 'timeEntries' in processed_data and 'error' in processed_data['timeEntries']:
            logger.warning(f"\nTime entries could not be fetched: {processed_data['timeEntries']['error']}")
        
        # Save to output file if specified
        if args.output:
            try:
                with open(args.output, 'w') as f:
                    json.dump(processed_data, f, indent=2)
                logger.info(f"\nTips, server sales, and time entries data saved to {args.output}")
            except Exception as e:
                error_msg = str(e)
                error_traceback = traceback.format_exc()
                logger.error(f"Error saving to output file: {error_msg}")
                logger.error(f"Traceback: {error_traceback}")
                send_error_to_webhook(
                    error_msg=f"Error saving to output file: {error_msg}",
                    error_traceback=error_traceback,
                    context="file_write"
                )
                raise
        
        # Send to webhook if requested
        if args.webhook:
            send_data_to_webhook(processed_data)
        
        # Send to response webhook if URL provided
        if args.response_webhook_url:
            send_data_to_webhook(processed_data, args.response_webhook_url)
        
        logger.info("Operation completed successfully.")
        logger.info("=" * 80)
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        logger.error(f"Error: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        # Send error to webhook
        send_error_to_webhook(
            error_msg=error_msg,
            error_traceback=error_traceback,
            context="main_execution"
        )
        
        logger.error("=" * 80)
        sys.exit(1)

if __name__ == "__main__":
    main()