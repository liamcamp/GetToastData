#!/usr/bin/env python3
"""
Main orchestrator script for the Toast API integration.
This script provides high-level control and configuration testing functionality.
"""

import sys
import argparse
import datetime
from server.toast_client import ToastAPIClient
from functions.get_orders.get_orders import process_orders_data, send_data_to_webhook

def test_configuration():
    """Test the Toast API configuration and authentication."""
    print("=" * 80)
    print("TESTING CONFIGURATION")
    print("=" * 80)
    
    try:
        print("\nInitializing Toast API client...")
        # Initialize Toast client - this will test authentication
        toast_client = ToastAPIClient()
        print("\nAuthentication test successful! Token was obtained.")
        
        # Test webhook configuration
        try:
            from config.config import WEBHOOK_URL
            print(f"\nWebhook URL is configured: {WEBHOOK_URL}")
        except (ImportError, AttributeError):
            print("\nWarning: Webhook URL not found in config.py, will use default URL")
            
        print("\nConfiguration test completed successfully.")
        print("=" * 80)
        return True
        
    except Exception as e:
        print(f"\nConfiguration test failed: {e}")
        print("\nPlease check your credentials and configuration.")
        print("=" * 80)
        return False

def main():
    """Main entry point for the Toast API integration."""
    parser = argparse.ArgumentParser(description='Toast API Integration Control Script')
    parser.add_argument('--test-config', action='store_true', help='Test configuration and authentication')
    args = parser.parse_args()
    
    if args.test_config:
        success = test_configuration()
        sys.exit(0 if success else 1)
    
    print("=" * 80)
    print(f"Toast API Integration - Started at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    print("\nAvailable functionality:")
    print("\n1. For order data:")
    print("   python get_orders.py [--date YYYY-MM-DD] [--process] [--webhook] [--output-file FILE]")
    print("\n4. To test configuration:")
    print("   python main.py --test-config")
    print("\nPlease use these scripts directly for their specific functionality.")
    print("=" * 80)

if __name__ == '__main__':
    main() 