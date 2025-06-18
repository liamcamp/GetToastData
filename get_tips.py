#!/usr/bin/env python3
"""
Toast Tips API Script - Tips and Server Sales Analysis

This script retrieves order information from the Toast Orders API and processes it to extract:
1. Total tips for each day in the specified date range
2. Total sales per server (by server.guid)

The script uses the same API infrastructure as get_orders.py with rate limiting protection.

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
        logging.FileHandler("get_tips.log"),
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
            "timestamp": datetime.datetime.utcnow().isoformat(),
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

def send_data_to_webhook(processed_data):
    """
    Send processed tips and server data to webhook.
    
    Args:
        processed_data: Processed tips and server data
    """
    # Webhook URL for tips data
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
    parser.add_argument('--debug', action='store_true', help='Enable detailed debugging output')
    
    args = parser.parse_args()
    
    # Validate that at least one output method is specified
    if not args.output and not args.webhook:
        parser.error("Must specify either --output-file or --webhook (or both)")
    
    # Set location index in environment if provided and not already set
    if args.location_index and not os.getenv('TOAST_LOCATION_INDEX'):
        os.environ['TOAST_LOCATION_INDEX'] = str(args.location_index)
        logger.info(f"Setting location index to {args.location_index}")
    
    return args

# Parse arguments and set location index before importing other modules
args = parse_args()

# Try to import ToastAPIClient from toast_client.py
try:
    from toast_client import ToastAPIClient
except ImportError:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from toast_client import ToastAPIClient
    except ImportError as e:
        logger.error(f"Failed to import ToastAPIClient: {str(e)}")
        error_traceback = traceback.format_exc()
        send_error_to_webhook(
            error_msg=f"Failed to import ToastAPIClient: {str(e)}",
            error_traceback=error_traceback,
            context="import_error"
        )
        raise

def process_tips_data(orders_data, location_index=None, date_range=None):
    """
    Process orders data to extract tips per day and sales per server.
    
    Args:
        orders_data: Raw orders data from Toast API
        location_index: Location index (1-5) to determine which restaurant to use
        date_range: Dict with 'start_date' and 'end_date' strings in YYYY-MM-DD format
        
    Returns:
        Dictionary with tips per day and sales per server
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
    
    # Initialize data structures
    tips_by_date = defaultdict(float)
    sales_by_server = defaultdict(float)
    server_guid_to_name = {}  # Store server GUID to name mapping if available
    
    # Track processing statistics
    total_orders_processed = 0
    total_payments_processed = 0
    orders_with_tips = 0
    
    logger.info(f"Processing {len(orders_data)} orders for tips and server sales...")
    
    # Loop through all orders
    for order in orders_data:
        total_orders_processed += 1
        order_has_tips = False
        
        # Extract date from payments.paidBusinessDate first (most reliable), then fall back to paidDate or openedDate
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
        
        # If date_range is provided, only process orders within the specified range
        if date_range:
            if order_date < date_range['start_date'] or order_date > date_range['end_date']:
                continue
        
        # Process each check in the order
        for check in order.get('checks', []):
            # Process each payment in the check
            for payment in check.get('payments', []):
                total_payments_processed += 1
                
                # Skip voided payments
                if payment.get('voidInfo') is not None:
                    continue
                
                # Extract tip amount
                tip_amount = float(payment.get('tipAmount', 0))
                if tip_amount > 0:
                    tips_by_date[order_date] += tip_amount
                    order_has_tips = True
                
                # Extract sales amount and server info
                payment_amount = float(payment.get('amount', 0))
                server_info = payment.get('server')
                
                if server_info and payment_amount > 0:
                    server_guid = server_info.get('guid')
                    if server_guid:
                        sales_by_server[server_guid] += payment_amount
                        
                        # Store server name if available (though it's not in the sample)
                        # This could be expanded if server names are available in the API response
                        if server_guid not in server_guid_to_name:
                            server_guid_to_name[server_guid] = f"Server_{server_guid[-8:]}"  # Use last 8 chars as identifier
        
        if order_has_tips:
            orders_with_tips += 1
    
    # Convert defaultdicts to regular dicts and sort
    tips_by_date_sorted = dict(sorted(tips_by_date.items()))
    sales_by_server_sorted = dict(sorted(sales_by_server.items()))
    
    # Create server summary with names
    server_summary = []
    for server_guid, total_sales in sales_by_server_sorted.items():
        server_summary.append({
            'server_guid': server_guid,
            'server_name': server_guid_to_name.get(server_guid, f"Server_{server_guid[-8:]}"),
            'total_sales': round(total_sales, 2)
        })
    
    # Calculate summary statistics
    total_tips = sum(tips_by_date.values())
    total_server_sales = sum(sales_by_server.values())
    
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
                'unique_servers': len(sales_by_server_sorted),
                'days_with_tips': len(tips_by_date_sorted)
            }
        },
        'location_index': location_index
    }
    
    # Log processing results
    logger.info(f"Processed {total_orders_processed} orders and {total_payments_processed} payments")
    logger.info(f"Found tips in {orders_with_tips} orders across {len(tips_by_date_sorted)} days")
    logger.info(f"Total tips: ${total_tips:.2f}")
    logger.info(f"Found sales data for {len(sales_by_server_sorted)} unique servers")
    logger.info(f"Total server sales: ${total_server_sales:.2f}")
    
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
            import config
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
        logger.info("SALES BY SERVER")
        logger.info("=" * 80)
        
        for server in processed_data['sales_by_server']:
            logger.info(f"{server['server_name']} ({server['server_guid']}): ${server['total_sales']:.2f}")
        
        logger.info(f"\nTotal Server Sales: ${processed_data['summary']['total_server_sales']:.2f}")
        
        # Save to output file if specified
        if args.output:
            try:
                with open(args.output, 'w') as f:
                    json.dump(processed_data, f, indent=2)
                logger.info(f"\nTips and server sales data saved to {args.output}")
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