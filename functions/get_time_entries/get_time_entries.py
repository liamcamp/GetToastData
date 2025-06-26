#!/usr/bin/env python3
"""
Toast Time Entries API Script - Time Entry Information Retrieval

This script allows you to retrieve time entry information from the Toast Labor API.
The script requires valid Toast API credentials and appropriate permissions to access labor data.

Prerequisites:
1. Valid Toast API credentials (client ID and client secret) configured in config.py
2. Restaurant GUID configured in config.py
3. Appropriate permissions to access labor data in Toast

Usage examples:
- Fetch time entries for today: python get_time_entries.py
- Fetch time entries for a specific date: python get_time_entries.py --dates 2025-03-03 2025-03-03
- Fetch time entries for a date range: python get_time_entries.py --dates 2025-03-01 2025-03-31
- Save results to a file: python get_time_entries.py --output-file timeEntries.json
- Use specific location: python get_time_entries.py --location-index 2

The script will output time entry details including clock in/out times, breaks, and employee information.
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

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "get_time_entries.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("toast-time-entries")

# Error webhook URL
ERROR_WEBHOOK_URL = "https://fynch.app.n8n.cloud/webhook/358766dc-09ae-4549-b762-f7079c0ac922"

def send_error_to_webhook(error_msg: str, error_traceback: str, context: str = "get_time_entries"):
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

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Fetch time entries data from Toast API')
    
    # Date parameters
    parser.add_argument('--dates', nargs=2, metavar=('START_DATE', 'END_DATE'), 
                       help='Specify date range in YYYY-MM-DD format (e.g., --dates 2025-01-01 2025-01-07)')
    
    parser.add_argument('--location-index', type=int, choices=range(1, 6),
                       help='Location index (1-5) to determine which restaurant GUID to use')
    parser.add_argument('--output-file', dest='output', help='Optional file to save time entries data')
    parser.add_argument('--include-archived', action='store_true', default=True,
                       help='Include archived time entries (default: True)')
    parser.add_argument('--include-missed-breaks', action='store_true', default=True,
                       help='Include missed breaks (default: True)')
    parser.add_argument('--time-entry-ids', help='Comma-separated list of time entry IDs to filter')
    parser.add_argument('--debug', action='store_true', help='Enable detailed debugging output')
    
    args = parser.parse_args()
    
    # Set location index in environment if provided and not already set
    if args.location_index and not os.getenv('TOAST_LOCATION_INDEX'):
        os.environ['TOAST_LOCATION_INDEX'] = str(args.location_index)
        logger.info(f"Setting location index to {args.location_index}")
    
    # Default to today if no dates provided
    if not args.dates:
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        args.dates = [today, today]
        logger.info(f"No dates specified, defaulting to today: {today}")
    
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

def process_time_entries_data(time_entries_data, location_index=None):
    """
    Process time entries data to extract basic information.
    
    Args:
        time_entries_data: Raw time entries data from Toast API
        location_index: Location index (1-5) to determine which location
        
    Returns:
        Dictionary with processed time entries information
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
    
    # Initialize summary data
    employee_summary = {}
    total_hours = 0.0
    total_entries = len(time_entries_data) if isinstance(time_entries_data, list) else 0
    
    print(f"Processing {total_entries} time entries...")
    
    # Process each time entry
    for entry in time_entries_data if isinstance(time_entries_data, list) else []:
        # Extract basic entry data
        employee_guid = entry.get('employeeGuid', 'Unknown')
        employee_name = entry.get('employeeName', 'Unknown Employee')
        clock_in = entry.get('clockInTime')
        clock_out = entry.get('clockOutTime')
        
        # Calculate hours worked if both clock in and out are available
        hours_worked = 0.0
        if clock_in and clock_out:
            try:
                # Parse timestamps
                clock_in_dt = datetime.datetime.fromisoformat(clock_in.replace('Z', '+00:00'))
                clock_out_dt = datetime.datetime.fromisoformat(clock_out.replace('Z', '+00:00'))
                
                # Calculate duration
                duration = clock_out_dt - clock_in_dt
                hours_worked = duration.total_seconds() / 3600  # Convert to hours
                total_hours += hours_worked
            except Exception as e:
                logger.warning(f"Error calculating hours for entry {entry.get('guid', 'unknown')}: {e}")
        
        # Track employee totals
        if employee_guid not in employee_summary:
            employee_summary[employee_guid] = {
                'name': employee_name,
                'total_hours': 0.0,
                'entries_count': 0,
                'entries': []
            }
        
        employee_summary[employee_guid]['total_hours'] += hours_worked
        employee_summary[employee_guid]['entries_count'] += 1
        employee_summary[employee_guid]['entries'].append({
            'guid': entry.get('guid'),
            'clockIn': clock_in,
            'clockOut': clock_out,
            'hoursWorked': round(hours_worked, 2),
            'businessDate': entry.get('businessDate'),
            'jobGuid': entry.get('jobGuid'),
            'breaks': entry.get('breaks', [])
        })
    
    # Convert employee summary to list format
    employees_result = []
    for employee_guid, data in employee_summary.items():
        employees_result.append({
            'employeeGuid': employee_guid,
            'employeeName': data['name'],
            'totalHours': round(data['total_hours'], 2),
            'entriesCount': data['entries_count'],
            'entries': data['entries']
        })
    
    # Sort by total hours (descending)
    employees_result.sort(key=lambda x: x['totalHours'], reverse=True)
    
    # Prepare result
    result = {
        'employees': employees_result,
        'summary': {
            'totalEntries': total_entries,
            'totalHours': round(total_hours, 2),
            'uniqueEmployees': len(employee_summary),
            'locationIndex': location_index
        }
    }
    
    logger.info(f"Processed {total_entries} time entries for {len(employee_summary)} unique employees")
    logger.info(f"Total hours across all entries: {total_hours:.2f}")
    
    return result

def main():
    """Main function to run the script"""
    args = parse_args()
    
    logger.info("=" * 80)
    logger.info(f"Toast Time Entries API Script - Started at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
        
        # Initialize the client
        logger.info("Initializing Toast API client...")
        client = ToastAPIClient()
        
        # Handle date parameters
        start_date_str, end_date_str = args.dates
        
        # Always use date range format as businessDate parameter causes 404 errors
        start_date = f"{start_date_str}T00:00:00.000Z"
        end_date = f"{end_date_str}T23:59:59.999Z"
        
        if start_date_str == end_date_str:
            logger.info(f"Fetching time entries for single date: {start_date_str}")
        else:
            logger.info(f"Fetching time entries from {start_date_str} to {end_date_str}")
        
        # Fetch time entries data using date range format
        time_entries_response = client.get_time_entries(
            start_date=start_date,
            end_date=end_date,
            include_archived=args.include_archived,
            include_missed_breaks=args.include_missed_breaks,
            time_entry_ids=args.time_entry_ids
        )
        
        # Extract time entries from response
        if isinstance(time_entries_response, dict):
            time_entries_data = time_entries_response.get('timeEntries', time_entries_response.get('data', []))
        elif isinstance(time_entries_response, list):
            time_entries_data = time_entries_response
        else:
            logger.warning(f"Unexpected response structure. Keys: {list(time_entries_response.keys()) if isinstance(time_entries_response, dict) else 'Not a dict'}")
            time_entries_data = []
        
        logger.info(f"Retrieved {len(time_entries_data)} time entries from Toast API")
        
        # Process the data
        processed_data = process_time_entries_data(time_entries_data, location_index)
        
        # Add date information to processed data
        processed_data['dateInfo'] = {
            "startDate": start_date_str,
            "endDate": end_date_str,
            "isDateRange": start_date_str != end_date_str
        }
        
        # Display summary
        logger.info("\n" + "=" * 80)
        logger.info("TIME ENTRIES SUMMARY")
        logger.info("=" * 80)
        
        summary = processed_data['summary']
        logger.info(f"Total Time Entries: {summary['totalEntries']}")
        logger.info(f"Unique Employees: {summary['uniqueEmployees']}")
        logger.info(f"Total Hours Worked: {summary['totalHours']:.2f}")
        logger.info(f"Location Index: {summary['locationIndex']}")
        
        # Display top employees by hours
        logger.info("\n" + "=" * 80)
        logger.info("TOP EMPLOYEES BY HOURS WORKED")
        logger.info("=" * 80)
        
        top_employees = processed_data['employees'][:10]  # Show top 10
        for i, emp in enumerate(top_employees, 1):
            logger.info(f"{i:2d}. {emp['employeeName']}: {emp['totalHours']:.2f} hours ({emp['entriesCount']} entries)")
        
        if len(processed_data['employees']) > 10:
            logger.info(f"... and {len(processed_data['employees']) - 10} more employees")
        
        # Display date range information
        date_info = processed_data['dateInfo']
        if date_info["isDateRange"]:
            logger.info(f"\nDate Range: {date_info['startDate']} to {date_info['endDate']}")
        else:
            logger.info(f"\nDate: {date_info['startDate']}")
        
        # Save data if output file specified
        if args.output:
            # Create output data structure
            output_data = {
                'timeEntries': time_entries_data,
                'processed': processed_data,
                'requestParameters': {
                    'startDate': start_date_str,
                    'endDate': end_date_str,
                    'locationIndex': location_index,
                    'includeArchived': args.include_archived,
                    'includeMissedBreaks': args.include_missed_breaks,
                    'timeEntryIds': args.time_entry_ids
                }
            }
            
            try:
                with open(args.output, 'w') as f:
                    json.dump(output_data, f, indent=2)
                logger.info(f"Time entries data saved to {args.output}")
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
        
        logger.info("\nOperation completed successfully.")
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