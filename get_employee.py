#!/usr/bin/env python3
"""
Toast Employee API Script - Employee Information Retrieval

This script allows you to retrieve employee information from the Toast Employee API.
The script requires valid Toast API credentials and appropriate permissions to access employee data.

Prerequisites:
1. Valid Toast API credentials (client ID and client secret) configured in config.py
2. Restaurant GUID configured in config.py
3. Appropriate permissions to access employee data in Toast

Usage examples:
- Fetch employee by GUID: python get_employee.py --guid 17f54cda-bbc4-43e9-ae6b-a2435d1abe74
- Save results to a file: python get_employee.py --guid 17f54cda-bbc4-43e9-ae6b-a2435d1abe74 --output-file employee.json
"""

import os
import sys
import argparse
import json
import datetime
import logging
import traceback
from typing import Dict, Any, Optional

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("get_employee.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("toast-employee")

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Fetch employee data from Toast API')
    
    parser.add_argument('--guid', help='Employee GUID to retrieve (optional - if not provided, fetches all employees)')
    parser.add_argument('--location-index', type=int, choices=range(1, 6),
                       help='Location index (1-5) to determine which restaurant GUID to use')
    parser.add_argument('--output-file', dest='output', help='Optional file to save employee data')
    parser.add_argument('--debug', action='store_true', help='Enable detailed debugging output')
    
    args = parser.parse_args()
    
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
        raise

def main():
    """Main function to run the script"""
    args = parse_args()
    
    logger.info("=" * 80)
    logger.info(f"Toast Employee API Script - Started at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
            logger.info(f"Using restaurant GUID: {config.TOAST_RESTAURANT_GUID} for location index {location_index}")
        except ImportError:
            logger.warning("Could not import config to verify restaurant GUID")
        
        if args.guid:
            logger.info(f"Fetching employee data for GUID: {args.guid}")
        else:
            logger.info("Fetching all employees")
        
        # First, let's try to decode the token to see what scopes we have
        try:
            import base64
            import json as json_lib
            
            # Get the token from the client
            token_parts = client.token.split('.')
            if len(token_parts) >= 2:
                # Decode the payload (second part of JWT)
                # Add padding if needed
                payload = token_parts[1]
                payload += '=' * (4 - len(payload) % 4)
                decoded_payload = base64.b64decode(payload)
                token_data = json_lib.loads(decoded_payload)
                
                logger.info("\n" + "=" * 80)
                logger.info("TOKEN INFORMATION")
                logger.info("=" * 80)
                
                if 'scopes' in token_data:
                    logger.info(f"Available scopes: {token_data['scopes']}")
                else:
                    logger.info("No 'scopes' field found in token")
                
                # Show other relevant fields
                for key in ['aud', 'exp', 'iat', 'iss', 'sub']:
                    if key in token_data:
                        logger.info(f"{key}: {token_data[key]}")
                
                logger.info("=" * 80)
            else:
                logger.warning("Token doesn't appear to be a valid JWT")
                
        except Exception as e:
            logger.warning(f"Could not decode token: {e}")
        
        # Try to fetch employee data
        try:
            employee_response = client.get_employee(args.guid)
        except Exception as e:
            logger.error(f"Employee API call failed: {e}")
            
            # Let's also try some other endpoints to see what we can access
            logger.info("\n" + "=" * 80)
            logger.info("TESTING OTHER ENDPOINTS FOR COMPARISON")
            logger.info("=" * 80)
            
            # Test orders endpoint (we know this works)
            try:
                logger.info("Testing orders endpoint...")
                today = datetime.datetime.now().strftime("%Y-%m-%d")
                start_date = f"{today}T00:00:00.000Z"
                end_date = f"{today}T23:59:59.999Z"
                orders_response = client.get_orders(start_date, end_date)
                logger.info("✓ Orders endpoint accessible")
            except Exception as orders_e:
                logger.error(f"✗ Orders endpoint failed: {orders_e}")
            
            # Test menus endpoint
            try:
                logger.info("Testing menus endpoint...")
                menus_response = client.get_menus()
                logger.info("✓ Menus endpoint accessible")
            except Exception as menus_e:
                logger.error(f"✗ Menus endpoint failed: {menus_e}")
            
            logger.info("=" * 80)
            
            # Re-raise the original employee API error
            raise
        
        # Display the employee information
        logger.info("\n" + "=" * 80)
        if args.guid:
            logger.info("EMPLOYEE INFORMATION")
        else:
            logger.info("ALL EMPLOYEES INFORMATION")
        logger.info("=" * 80)
        
        if isinstance(employee_response, list):
            if len(employee_response) == 0:
                logger.info("No employees found")
            else:
                logger.info(f"Found {len(employee_response)} employee(s)")
                for i, employee in enumerate(employee_response):
                    logger.info(f"\n--- Employee {i+1} ---")
                    if isinstance(employee, dict):
                        for key, value in employee.items():
                            logger.info(f"{key}: {value}")
                    else:
                        logger.info(f"Employee data: {employee}")
        elif isinstance(employee_response, dict):
            # Single employee or response wrapper
            if 'employees' in employee_response:
                employees = employee_response['employees']
                logger.info(f"Found {len(employees)} employee(s)")
                for i, employee in enumerate(employees):
                    logger.info(f"\n--- Employee {i+1} ---")
                    if isinstance(employee, dict):
                        for key, value in employee.items():
                            logger.info(f"{key}: {value}")
                    else:
                        logger.info(f"Employee data: {employee}")
            else:
                # Single employee
                for key, value in employee_response.items():
                    logger.info(f"{key}: {value}")
        else:
            logger.error("Unexpected response format from employee API")
            logger.info(f"Employee data: {employee_response}")
        
        logger.info("=" * 80)
        
        # If debug mode is enabled, show the raw response
        if args.debug:
            logger.info("\n" + "=" * 80)
            logger.info("RAW API RESPONSE")
            logger.info("=" * 80)
            logger.info(json.dumps(employee_response, indent=2))
            logger.info("=" * 80)
        
        # Save data if output specified
        if args.output:
            try:
                with open(args.output, 'w') as f:
                    json.dump(employee_response, f, indent=2)
                logger.info(f"Employee data saved to {args.output}")
            except Exception as e:
                logger.error(f"Error saving to output file: {str(e)}")
                raise
        
        logger.info("Operation completed successfully.")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        logger.error("=" * 80)
        sys.exit(1)

if __name__ == "__main__":
    main()