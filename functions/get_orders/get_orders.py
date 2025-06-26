#!/usr/bin/env python3
"""
Toast Orders API Script - Order Information Retrieval

This script allows you to retrieve order information from the Toast Orders API.
The script requires valid Toast API credentials and appropriate permissions to access order data.

Recent updates:
- Added handling of voided items to exclude them from totals
- Raw item prices × quantities are used without discount adjustments
- Maintained category-based aggregation for informational purposes
- Added error logging and webhook error reporting

Prerequisites:
1. Valid Toast API credentials (client ID and client secret) configured in config.py
2. Restaurant GUID configured in config.py
3. Appropriate permissions to access order data in Toast

Usage examples:
- Fetch orders for today: python get_orders.py
- Fetch orders for a specific date: python get_orders.py --date 2025-03-03
- Save results to a file: python get_orders.py --output-file orders.json
- Save processed results to a file: python get_orders.py --output-file processed_orders.json --process
- Post results to webhook: python get_orders.py --webhook

The script will output order details excluding voided items, but without applying discounts.
This provides a foundation that can be later extended to include discount handling.
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
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "get_orders.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("toast-orders")

# Error webhook URL
ERROR_WEBHOOK_URL = "https://fynch.app.n8n.cloud/webhook/358766dc-09ae-4549-b762-f7079c0ac922"

def send_error_to_webhook(error_msg: str, error_traceback: str, context: str = "get_orders"):
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

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Fetch orders data from Toast API')
    
    # Create a mutually exclusive group for date parameters
    date_group = parser.add_mutually_exclusive_group()
    date_group.add_argument('--date', help='Specify a single date in YYYY-MM-DD format (default: today)')
    date_group.add_argument('--dates', nargs=2, metavar=('START_DATE', 'END_DATE'), 
                        help='Specify date range in YYYY-MM-DD format (e.g., --dates 2025-01-01 2025-01-07)')
    
    parser.add_argument('--location-index', type=int, choices=range(1, 6),
                       help='Location index (1-5) to determine which restaurant GUID to use')
    parser.add_argument('--output-file', dest='output', help='Optional file to save orders data')
    parser.add_argument('--process', action='store_true', help='Process the data to show item sales summary')
    parser.add_argument('--webhook', action='store_true', help='Send processed data to webhook')
    parser.add_argument('--webhook-url', help='Custom webhook URL to send data to (optional, uses default if not specified)')
    parser.add_argument('--items-csv', action='store_true',
                        help='Output only item names to a CSV file (other output options will be ignored)')
    parser.add_argument('--debug', action='store_true', help='Enable detailed debugging output')
    
    args = parser.parse_args()
    
    # Set location index in environment if provided and not already set
    if args.location_index and not os.getenv('TOAST_LOCATION_INDEX'):
        os.environ['TOAST_LOCATION_INDEX'] = str(args.location_index)
        logger.info(f"Setting location index to {args.location_index}")
    
    return args

# Parse arguments and set location index before importing other modules
args = parse_args()

# Now import the rest of the modules

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

def process_orders_data(orders_data, location_index=None):
    """
    Process orders data to extract basic information, applying discounts to sales figures.
    Returns data from the API excluding voided items and gift cards with discounts applied.
    
    Args:
        orders_data: Raw orders data from Toast API
        location_index: Location index (1-5) to determine which category map to use
        
    Returns:
        Dictionary with items and category information with discounts applied
    """
    item_summary = {}
    
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
    
    # Location-specific category GUID maps
    location_category_maps = {
        # Location 1 (Elena's - West Portal)
        1: {
            "bcd1b36a-8ff1-48cf-9190-084cc0c78776": "Food",
            "ad216e1f-aae1-4c7e-a664-7bd1497bea2f": "NA Beverage",
            "59c5ad7d-a3c2-48a9-bc4a-b7a1217f6592": "Liquor",
            "b931698b-5fd1-44a1-9b51-8e013202cc8e": "Draft Beer",
            "1d06f0a0-6643-4942-aace-9de852bcd5a2": "Bottled Beer",
            "3276434c-d165-4c43-90f8-9a3032dcf5a7": "Wine"
        },
        # Location 2 (Little Original Joe's - West Portal)
        2: {
            "32a8246e-febc-46fd-aead-ea4f3e88d258": "Food",
            "739c715d-3c4f-4230-ae68-0abac14fa9d4": "Market",
            "89911839-70f0-43fc-af9d-582fbf906ddb": "Wine Bottle"
        },
        # Location 3 (Little Original Joe's - Marina)
        3: {
            "53269235-c054-45f6-9f63-ece5dac6a174": "Food",
            "adba1578-989b-4f8c-b300-6f516bbf0065": "NA Beverage",
            "1f58d463-1610-4032-8b05-003e2d9fb828": "Liquor",
            "1d9b2997-0a7c-41ae-b995-c19823c584f6": "Beer Bottle",
            "e67839f8-4e28-4d42-9e9c-34b40787fb6b": "Beer Keg",
            "681460a5-608f-42b5-bdbb-f6a9263d92f2": "Wine Bottle",
            "57f0e230-b508-4406-ba2d-0210a60aabc4": "Wine Keg",
        },
        # Location 4 (Original Joe's - North Beach)
        4: {
            "758a34df-b27f-419a-81b8-2c56a663f15b": "Food",
            "64a6a7fb-f3ce-4f2f-936d-39118bda785f": "NA Beverage",
            "dc3bad48-66ff-4183-9cd3-7a3552ab5973": "Liquor",
            "ef6790cb-64f3-4887-84b2-fd348dac46a9": "Beer Bottle",
            "fcd1cbdc-361f-4f66-93f2-53467adfd134": "Beer Keg",
            "d0ea6c37-bf62-415a-a40d-6a4a824bb661": "Wine Bottle",
            "3e611002-7c96-4b20-a228-a05efc70c2c3": "Wine Keg",
            
        },
        # Location 5 (Original Joe's - Westlake)
        5: {
            "87cad208-2fe9-4099-ba3d-da367a951b05": "Food",
            "6a7eb3d6-27d0-44d2-883b-c2615ac13f1a": "NA Beverage",
            "5b57fb6c-89fb-404f-8358-357cc51c62bd": "Liquor",
            "30a4bc57-ad0c-466a-887d-5ea0387c1efc": "Beer Bottle",
            "e4566b76-1f88-4e8c-a90d-2f8a00543f04": "Beer Keg",
            "d647c1b5-e55d-4b3e-b1b0-c2272fbc75ee": "Wine Bottle",
            "30812d57-5b44-48a0-8150-498d6287d5d3": "Wine Keg",
        }
    }
    
    # Get the category map for the current location
    category_guid_map = location_category_maps.get(location_index, location_category_maps[4])  # Default to location 4 if not found
    
    # Location-specific category initialization dictionaries
    location_category_initializations = {
        # Location 1 (Elena's - West Portal)
        1: {
            "Food": 0.0,
            "NA Beverage": 0.0,
            "Liquor": 0.0,
            "Draft Beer": 0.0,
            "Bottled Beer": 0.0,
            "Wine": 0.0,
            "Corkage Fee": 0.0,
            "Other": 0.0
        },
        # Location 2 (Little Original Joe's - West Portal)
        2: {
            "Food": 0.0,
            "Market": 0.0,
            "NA Beverage": 0.0,
            "Liquor": 0.0,
            "Beer Bottle": 0.0,
            "Beer Keg": 0.0,
            "Wine Bottle": 0.0,
            "Wine Keg": 0.0,
            "Corkage Fee": 0.0,
            "Other": 0.0
        },
        3: {
            "Food": 0.0,
            "NA Beverage": 0.0,
            "Liquor": 0.0,
            "Beer Bottle": 0.0,
            "Beer Keg": 0.0,
            "Wine Bottle": 0.0,
            "Wine Keg": 0.0,
            "Corkage Fee": 0.0,
            "Other": 0.0
        },
        4: {
            "Food": 0.0,
            "NA Beverage": 0.0,
            "Liquor": 0.0,
            "Beer Bottle": 0.0,
            "Beer Keg": 0.0,
            "Wine Bottle": 0.0,
            "Wine Keg": 0.0,
            "Corkage Fee": 0.0,
            "Other": 0.0
        },
        5: {
            "Food": 0.0,
            "NA Beverage": 0.0,
            "Liquor": 0.0,
            "Beer Bottle": 0.0,
            "Beer Keg": 0.0,
            "Wine Bottle": 0.0,
            "Wine Keg": 0.0,
            "Corkage Fee": 0.0,
            "Other": 0.0
        }
    }
    
    # Get the category initialization dictionary for the current location
    category_init = location_category_initializations.get(location_index, location_category_initializations[4])
    
    # Initialize category totals (these will now include applied discounts)
    category_totals = category_init.copy()
    
    # Initialize raw category totals (before discounts)
    raw_category_totals = category_init.copy()
    
    # Initialize category discounts
    category_discounts = category_init.copy()
    
    # Initialize category item counts (convert float values to integers)
    category_item_counts = {k: int(v) for k, v in category_init.items()}
    
    # Initialize category service charges
    category_service_charges = category_init.copy()
    
    # Track voided items count and gift card items count
    voided_items_count = 0
    gift_card_items_count = 0
    
    # Track non-gratuity service charges
    total_non_grat_service_charges = 0.0
    
    print(f"Processing {len(orders_data)} orders (excluding voided items and gift cards)...")
    
    # Loop through all orders
    for order in orders_data:
        # Process service charges first
        for check in order.get('checks', []):
            for service_charge in check.get('appliedServiceCharges', []):
                # Only include non-gratuity service charges
                if not service_charge.get('gratuity', False):
                    charge_value = service_charge.get('chargeAmount') # Get value, could be None
                    charge_amount = float(charge_value) if charge_value is not None else 0.0 # Handle None
                    total_non_grat_service_charges += charge_amount
        
        # Process each check in the order
        for check in order.get('checks', []):
            # Calculate total subtotal for this check
            check_subtotal = sum(
                float(selection.get('preDiscountPrice', 0))
                for selection in check.get('selections', [])
                if not selection.get('voided', False)
                and selection.get('displayName', '').strip() not in ['Gift Card', 'eGift Card', 'Add Value ($)']
            )
            
            # Process each selection (menu item) in the check
            for selection in check.get('selections', []):
                # Skip voided selections
                if selection.get('voided', False):
                    voided_items_count += 1
                    continue
                
                # Skip gift card items (both regular and eGift cards)
                display_name = selection.get('displayName', '').strip()
                if display_name in ['Gift Card', 'eGift Card', 'Add Value ($)']:
                    gift_card_items_count += 1
                    continue
                    
                # Extract basic item data
                item_name = selection.get('displayName', 'Unknown Item')
                quantity = float(selection.get('quantity', 0))
                base_price = float(selection.get('receiptLinePrice', 0))
                
                # Get the salesCategory GUID for categorization
                sales_category_guid = None
                if 'salesCategory' in selection and selection['salesCategory'] is not None:
                    sales_category_guid = selection['salesCategory'].get('guid')
                
                # Calculate raw price without discount adjustments
                raw_total_price = float(selection.get('preDiscountPrice', 0))
                
                # Determine the category based on salesCategory GUID
                category = "Other"  # Default category
                
                # Handle "Corkage Fee" items specifically
                if item_name == "Corkage Fee":
                    category = "Corkage Fee"
                elif sales_category_guid in category_guid_map:
                    category = category_guid_map[sales_category_guid]

                # <<< START MODIFICATION FOR API SOURCE WORKAROUND >>>
                # If the category defaulted to 'Other' AND the order source is 'API',
                # re-assign the category to 'Food' as a workaround for missing salesCategory data.
                # Apply this ONLY for Location 4 where the issue is known.
                # Ensure 'order' object is accessible here - it should be from the outer loop
                order_source = order.get("source") # Get the source from the parent order object
                if category == "Other" and order_source == "API" and location_index == 4:
                    logger.debug(f"API Workaround applied: Item '{item_name}' re-categorized from 'Other' to 'Food' for Location 4 because order source is 'API'.")
                    category = "Food" # Re-assign to Food category

                # <<< END MODIFICATION FOR API SOURCE WORKAROUND >>>

                # Process discounts according to the requirements
                applied_discounts = selection.get('appliedDiscounts', [])
                item_discount = 0.0
                
                if applied_discounts:
                    # Check if there are any non-voided discounts
                    has_non_voided_discounts = False
                    for discount in applied_discounts:
                        if discount.get('processingState') != "VOID":
                            has_non_voided_discounts = True
                            discount_amount = float(discount.get('discountAmount', 0))
                            item_discount += discount_amount
                    
                    # If no non-voided discounts found, calculate from price difference
                    if not has_non_voided_discounts:
                        pre_discount_price = float(selection.get('preDiscountPrice', 0))
                        price = float(selection.get('price', 0))
                        item_discount = pre_discount_price - price
                else:
                    # If no discounts at all, calculate from price difference
                    pre_discount_price = float(selection.get('preDiscountPrice', 0))
                    price = float(selection.get('price', 0))
                    item_discount = pre_discount_price - price
                
                # Calculate discounted total price
                discounted_total_price = raw_total_price - item_discount
                
                # Add the discounts to the category tracking
                if item_discount > 0:
                    category_discounts[category] += item_discount
                
                # Add to raw category totals
                raw_category_totals[category] += raw_total_price
                
                # Add to category totals with discounts applied
                category_totals[category] += discounted_total_price
                
                # Increment the item count for this category
                category_item_counts[category] += quantity
                
                # Calculate and add service charges for this item
                if check_subtotal > 0:
                    item_percentage = raw_total_price / check_subtotal
                    for service_charge in check.get('appliedServiceCharges', []):
                        if not service_charge.get('gratuity', False):
                            charge_value = service_charge.get('chargeAmount') # Get value, could be None
                            charge_amount = float(charge_value) if charge_value is not None else 0.0 # Handle None
                            attributed_charge = charge_amount * item_percentage
                            category_service_charges[category] += attributed_charge
                
                # Add to our aggregated data
                if item_name in item_summary:
                    item_summary[item_name]['quantity'] += quantity
                    item_summary[item_name]['raw_sales'] += raw_total_price
                    item_summary[item_name]['discounts'] += item_discount
                    item_summary[item_name]['net_sales'] += discounted_total_price
                else:
                    item_summary[item_name] = {
                        'quantity': quantity,
                        'raw_sales': raw_total_price,
                        'net_sales': discounted_total_price,
                        'unit_price': base_price,
                        'category': category,
                        'category_guid': sales_category_guid,
                        'discounts': item_discount
                    }
    
    # Convert the summary to the desired output format
    items_result = []
    for item_name, data in item_summary.items():
        # Check if the quantity is a whole number
        quantity_value = data['quantity']
        # Format as an integer if it's a whole number
        if quantity_value == int(quantity_value):
            quantity = int(quantity_value)
        else:
            quantity = quantity_value
        
        items_result.append({
            'name': item_name,
            'quantity': quantity,
            'raw_sales': round(data['raw_sales'], 2),
            'net_sales': round(data['net_sales'], 2),
            'unit_price': round(data['unit_price'], 2),
            'category': data['category'],
            'category_guid': data['category_guid'],
            'discounts': round(data['discounts'], 2)
        })
    
    # Round all category totals to 2 decimal places
    for category in category_totals:
        category_totals[category] = round(category_totals[category], 2)
        raw_category_totals[category] = round(raw_category_totals[category], 2)
        category_discounts[category] = round(category_discounts[category], 2)
        category_service_charges[category] = round(category_service_charges[category], 2)
    
    # Calculate the total discount across all categories
    total_discount_amount = sum(category_discounts.values())
    
    # Add the total discount to the category_discounts dictionary
    category_discounts['Total'] = round(total_discount_amount, 2)
    
    # Round total service charges
    total_non_grat_service_charges = round(total_non_grat_service_charges, 2)
    
    # Calculate total_sales (net_sales + category_discounts)
    total_sales = {}
    for category_key in category_totals:
        total_sales[category_key] = round(
            category_totals[category_key] + 
            category_discounts[category_key], # Uses original per-category discount
            2
        )

    # Calculate the sum of (net_sales + discounts) for ALL actual categories. This is for logging.
    sum_for_logging_total_sales_plus_discounts = sum(total_sales.values())

    # Calculate the sum of all 'total_sales' entries, excluding 'Other', for the new 'total' attribute.
    grand_total_sales_excluding_other = 0.0
    for cat_name, cat_total_value in total_sales.items(): # Iterate the per-category values just computed
        if cat_name != "Other":
            grand_total_sales_excluding_other += cat_total_value
    
    # Add the new 'total' attribute (lowercase as requested) to the total_sales dictionary.
    # This 'total_sales' dictionary will go into the result.
    total_sales['total'] = round(grand_total_sales_excluding_other, 2)
    
    # Prepare result with items and category info
    result = {
        'items': items_result,
        'net_sales': category_totals,  # These now have discounts applied
        'gross_sales': raw_category_totals,  # These are pre-discount totals
        'category_counts': category_item_counts,
        'category_discounts': category_discounts, # This category_discounts includes 'Total'
        'voided_items_count': voided_items_count,
        'gift_card_items_count': gift_card_items_count,
        'nonGratServiceCharges': total_non_grat_service_charges,
        'nonGratServiceChargesAggregates': category_service_charges,
        'total_sales': total_sales,  # This dict now includes per-category values AND the 'total' key
        'locationIndex': location_index
    }
    
    logger.info(f"Processed data into {len(items_result)} unique menu items across {len(category_totals)} categories")
    logger.info(f"Excluded {voided_items_count} voided items from totals")
    logger.info(f"Excluded {gift_card_items_count} gift card items from totals")
    # Corrected Log for total discounts applied:
    logger.info(f"Total discounts applied: ${category_discounts['Total']:.2f}")
    logger.info(f"Total sales after discounts (Net Sales): ${sum(category_totals.values()):.2f}") # Sum of net_sales is fine
    logger.info(f"Total non-gratuity service charges: ${total_non_grat_service_charges:.2f}")
    # Corrected log for "Total sales (net sales + discounts)" using the sum calculated *before* 'total' key was added
    logger.info(f"Total sales (net sales + discounts): ${sum_for_logging_total_sales_plus_discounts:.2f}") 
    logger.info(f"Location index: {location_index}")
    
    return result


def send_data_to_webhook(processed_data, webhook_url=None):
    """
    Send processed order data to a webhook.
    
    Args:
        processed_data: Processed orders data 
        webhook_url: Optional webhook URL to override default
    """
    # Default webhook URL - override with config or parameter
    if webhook_url is None:
        try:
            from config.config import WEBHOOK_URL
            webhook_url = WEBHOOK_URL
        except (ImportError, AttributeError):
            webhook_url = "https://fynch.app.n8n.cloud/webhook/296efd56-83d2-4817-a750-0a55eae41da6"
    
    item_count = len(processed_data['items']) if isinstance(processed_data, dict) and 'items' in processed_data else len(processed_data)
    logger.info(f"Sending data with {item_count} unique items to webhook: {webhook_url}")
    
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


def main():
    """Main function to run the script"""
    args = parse_args()
    
    logger.info("=" * 80)
    logger.info(f"Toast Orders API Script - Started at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
        
        # Store date information for the webhook
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
            total_voided_items = 0
            total_gift_card_items = 0
            
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
            
            # Store date info for webhook
            date_info = {
                "startDate": start_date_str,
                "endDate": end_date_str,
                "isDateRange": True
            }
            
            # Process all orders together
            orders_data = all_orders
            total_count = len(orders_data)
            
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
            
            # Store date info for webhook
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
                total_count = orders_response.get('totalCount', len(orders_data))
            elif isinstance(orders_response, list):
                orders_data = orders_response
                total_count = len(orders_data)
            else:
                logger.warning(f"Unexpected response structure. Keys: {list(orders_response.keys()) if isinstance(orders_response, dict) else 'Not a dict'}")
                orders_data = []
                total_count = 0
            
            logger.info(f"Retrieved {len(orders_data)} orders from Toast API")
        
        # Process the data
        processed_data = process_orders_data(orders_data, location_index)
        
        # Add date information to processed data
        processed_data['dateInfo'] = date_info
        
        # Handle special case for items-csv output
        if args.items_csv:
            # Get the list of unique item names
            items = [item['name'] for item in processed_data['items']]
            
            # Determine output filename
            if args.output:
                # Ensure the file ends with .csv
                csv_filename = args.output
                if not csv_filename.lower().endswith('.csv'):
                    csv_filename = f"{os.path.splitext(csv_filename)[0]}.csv"
            else:
                # Default filename
                if date_info["isDateRange"]:
                    csv_filename = f"ordered_items_{date_info['startDate']}_to_{date_info['endDate']}.csv"
                else:
                    csv_filename = f"ordered_items_{date_info['startDate']}.csv"
            
            # Write the simple CSV file with only item names
            try:
                with open(csv_filename, 'w') as f:
                    for item_name in items:
                        f.write(f"{item_name}\n")
                
                logger.info(f"Successfully wrote {len(items)} item names to {csv_filename}")
                logger.info("Operation completed successfully.")
                logger.info("=" * 80)
                return
            except Exception as e:
                error_msg = str(e)
                error_traceback = traceback.format_exc()
                logger.error(f"Error writing to CSV file: {error_msg}")
                logger.error(f"Traceback: {error_traceback}")
                send_error_to_webhook(
                    error_msg=f"Error writing to CSV file: {error_msg}",
                    error_traceback=error_traceback,
                    context="csv_write"
                )
                raise
        
        # Continue with normal output for non-CSV cases
        
        # Display aggregates
        logger.info("\n" + "=" * 80)
        logger.info("SALES AGGREGATES BY CATEGORY (Excluding Voided Items)")
        logger.info("=" * 80)
        
        # Get the categories we want to highlight
        main_categories = [
            "Food", 
            "Draft Beer", 
            "Bottled Beer", 
            "Wine", 
            "Liquor", 
            "NA Beverage",
            "Corkage Fee"
        ]
        
        total_sales = 0
        total_items = 0
        total_discounts = 0
        total_net_sales = 0
        total_service_charges = 0
        
        # Display each main category
        for category in main_categories:
            amount = processed_data['net_sales'].get(category, 0)
            item_count = processed_data['category_counts'].get(category, 0)
            discounts = processed_data['category_discounts'].get(category, 0)
            service_charges = processed_data['nonGratServiceChargesAggregates'].get(category, 0)
            total = processed_data['total_sales'].get(category, 0)
            
            total_sales += total
            total_items += item_count
            total_discounts += discounts
            total_net_sales += amount
            total_service_charges += service_charges
            
            # Only show discounts if they exist for this category
            if discounts > 0:
                logger.info(f"{category}: ${amount:.2f} ({item_count} items) - Discounts: ${discounts:.2f} - Service Charges: ${service_charges:.2f} - Total: ${total:.2f}")
            else:
                logger.info(f"{category}: ${amount:.2f} ({item_count} items) - Service Charges: ${service_charges:.2f} - Total: ${total:.2f}")
        
        # Also show the "Other" category if it has any value
        other_amount = processed_data['net_sales'].get("Other", 0)
        other_count = processed_data['category_counts'].get("Other", 0)
        other_discounts = processed_data['category_discounts'].get("Other", 0)
        other_service_charges = processed_data['nonGratServiceChargesAggregates'].get("Other", 0)
        other_total = processed_data['total_sales'].get("Other", 0)
        
        if other_amount > 0 or other_count > 0:
            total_sales += other_total
            total_items += other_count
            total_discounts += other_discounts
            total_net_sales += other_amount
            total_service_charges += other_service_charges
            
            if other_discounts > 0:
                logger.info(f"Other: ${other_amount:.2f} ({other_count} items) - Discounts: ${other_discounts:.2f} - Service Charges: ${other_service_charges:.2f} - Total: ${other_total:.2f}")
            else:
                logger.info(f"Other: ${other_amount:.2f} ({other_count} items) - Service Charges: ${other_service_charges:.2f} - Total: ${other_total:.2f}")
        
        # Display grand total
        logger.info("-" * 80)
        logger.info(f"TOTAL SALES: ${total_sales:.2f} (TOTAL ITEMS: {total_items})")
        logger.info(f"NET SALES: ${total_net_sales:.2f}")
        logger.info(f"TOTAL DISCOUNTS: ${total_discounts:.2f}")
        logger.info(f"TOTAL SERVICE CHARGES: ${total_service_charges:.2f}")
        logger.info(f"FINAL TOTAL (net - service charges + discounts): ${total_sales:.2f}")
        logger.info("=" * 80)
        
        # Print date range information
        if date_info["isDateRange"]:
            logger.info(f"Date Range: {date_info['startDate']} to {date_info['endDate']}")
        else:
            logger.info(f"Date: {date_info['startDate']}")
        
        logger.info("\n" + "=" * 80)
        logger.info("IMPORTANT NOTES ABOUT DATA")
        logger.info("=" * 80)
        logger.info("This output contains raw data with the following processing:")
        logger.info(f"- Excluded {processed_data.get('voided_items_count', 0)} voided items")
        logger.info("- Discounts have been calculated and shown separately")
        logger.info("- No modifiers have been added to prices")
        logger.info("- Raw item prices × quantities are used")
        logger.info("=" * 80)
        
        # Always print information about the comprehensive items list
        items_count = len(processed_data['items'])
        logger.info(f"COMPREHENSIVE ITEMS LIST: {items_count} unique items ordered")
        logger.info("-" * 40)
        
        # Show a sample of items regardless of process flag
        sample_size = min(5, items_count)
        if sample_size > 0:
            logger.info("Sample items:")
            for item in processed_data['items'][:sample_size]:
                if item['discounts'] > 0:
                    logger.info(f"  {item['name']}: {item['quantity']} units, ${item['net_sales']:.2f} total, ${item['discounts']:.2f} discounts")
                else:
                    logger.info(f"  {item['name']}: {item['quantity']} units, ${item['net_sales']:.2f} total")
            
            if items_count > sample_size:
                logger.info(f"  ... and {items_count - sample_size} more items")
            logger.info("-" * 40)
        logger.info(f"The complete items list will be included in output file and/or webhook data.")
        logger.info("=" * 40)
        
        # If debug mode is enabled, show some additional raw data information
        if args.debug:
            logger.info("\n" + "=" * 80)
            logger.info("DEBUGGING INFORMATION")
            logger.info("=" * 80)
            
            # Calculate the total from items to verify consistency
            total_from_items = sum(item['net_sales'] for item in processed_data['items'])
            total_discounts_from_items = sum(item['discounts'] for item in processed_data['items'])
            
            logger.info(f"Total calculated from items: ${total_from_items:.2f}")
            logger.info(f"Total calculated from categories: ${total_sales:.2f}")
            logger.info(f"Total discounts from items: ${total_discounts_from_items:.2f}")
            logger.info(f"Total discounts from categories: ${total_discounts:.2f}")
            
            # Check if there are any voided orders in the raw data (not just selections)
            voided_orders_count = sum(1 for order in orders_data if order.get('voided', False))
            logger.info(f"Number of voided orders in raw data: {voided_orders_count}")
            logger.info(f"Number of voided menu items excluded: {processed_data.get('voided_items_count', 0)}")
            
            logger.info("=" * 80)
        
        # Process further details if requested
        if args.process:
            # We already displayed a sample of items above, so no need to repeat
            
            # Save processed data if output specified
            if args.output:
                try:
                    with open(args.output, 'w') as f:
                        json.dump(processed_data, f, indent=2)
                    logger.info(f"Raw processed orders data saved to {args.output}")
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
            send_data_to_webhook(processed_data, args.webhook_url)
        
        # Save raw data if output specified and not already saved processed data
        elif args.output and not args.process:
            # Create output data with items always included
            if isinstance(orders_data, list):
                output_data = {
                    'orders': orders_data,
                    'items': processed_data['items'],
                    'net_sales': processed_data['net_sales'],
                    'gross_sales': processed_data['gross_sales'],
                    'category_counts': processed_data['category_counts'],
                    'category_discounts': processed_data['category_discounts'],
                    'dateInfo': date_info,
                    'nonGratServiceCharges': processed_data['nonGratServiceCharges'],
                    'nonGratServiceChargesAggregates': processed_data['nonGratServiceChargesAggregates'],
                    'total_sales': processed_data['total_sales']
                }
            else:
                output_data = orders_data
                output_data['items'] = processed_data['items']
                output_data['net_sales'] = processed_data['net_sales']
                output_data['gross_sales'] = processed_data['gross_sales']
                output_data['category_counts'] = processed_data['category_counts']
                output_data['category_discounts'] = processed_data['category_discounts']
                output_data['dateInfo'] = date_info
                output_data['nonGratServiceCharges'] = processed_data['nonGratServiceCharges']
                output_data['nonGratServiceChargesAggregates'] = processed_data['nonGratServiceChargesAggregates']
                output_data['total_sales'] = processed_data['total_sales']
            
            try:
                with open(args.output, 'w') as f:
                    json.dump(output_data, f, indent=2)
                logger.info(f"Raw orders data with basic aggregates saved to {args.output}")
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