#!/usr/bin/env python3
"""
Toast API Authentication Test Script

This script tests authentication with the Toast API and prints detailed debugging information.
It can help identify issues with credentials or API connectivity.
"""
import os
import sys
import datetime
import requests
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_auth():
    """Test authentication with Toast API and print detailed information."""
    print("=" * 80)
    print("TOAST API AUTHENTICATION TEST")
    print("=" * 80)
    
    # Get credentials from environment
    client_id = os.getenv('TOAST_CLIENT_ID')
    client_secret = os.getenv('TOAST_CLIENT_SECRET')
    auth_url = os.getenv('TOAST_AUTH_URL')
    restaurant_guid = os.getenv('TOAST_RESTAURANT_GUID')
    api_base_url = os.getenv('TOAST_API_BASE_URL')
    
    # Check if credentials are set
    missing = []
    if not client_id: missing.append('TOAST_CLIENT_ID')
    if not client_secret: missing.append('TOAST_CLIENT_SECRET')
    if not auth_url: missing.append('TOAST_AUTH_URL')
    if not restaurant_guid: missing.append('TOAST_RESTAURANT_GUID')
    if not api_base_url: missing.append('TOAST_API_BASE_URL')
    
    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        print("Please check your .env file and make sure all required variables are set.")
        return False
    
    # Print environment settings (but mask secrets)
    print("\nEnvironment Settings:")
    print(f"TOAST_CLIENT_ID: {client_id[:5]}...{client_id[-4:] if len(client_id) > 9 else ''}")
    print(f"TOAST_CLIENT_SECRET: {client_secret[:5]}...{client_secret[-4:] if len(client_secret) > 9 else ''}")
    print(f"TOAST_AUTH_URL: {auth_url}")
    print(f"TOAST_RESTAURANT_GUID: {restaurant_guid}")
    print(f"TOAST_API_BASE_URL: {api_base_url}")
    
    # Prepare authentication request
    payload = {
        "clientId": client_id,
        "clientSecret": client_secret,
        "userAccessType": "TOAST_MACHINE_CLIENT"
    }
    
    headers = {"Content-Type": "application/json"}
    
    # Make the authentication request
    print("\nSending authentication request...")
    
    try:
        response = requests.post(
            auth_url,
            json=payload,
            headers=headers
        )
        
        print(f"Response status code: {response.status_code}")
        
        if response.status_code == 200:
            auth_data = response.json()
            
            print(f"Authentication SUCCESS!")
            print(f"Response contains keys: {', '.join(auth_data.keys())}")
            
            # Dump full response structure for debugging
            print(f"\nFull authentication response: {json.dumps(auth_data, indent=2)}")
            
            # Extract the access token from the nested structure
            access_token = None
            token_data = auth_data.get('token')
            
            if isinstance(token_data, dict):
                access_token = token_data.get('accessToken')
                print(f"Found accessToken in nested token object")
            elif isinstance(auth_data.get('token'), str):
                access_token = auth_data.get('token')
                print(f"Found direct token string")
                
            if access_token:
                # Safely show part of the token
                token_preview = access_token[:10] + "..." if isinstance(access_token, str) else "Not a string"
                print(f"Token received: {token_preview}")
                print("\nNow testing an API call with this token...")
                
                # Try a simple API call to validate the token
                api_headers = {
                    "Toast-Restaurant-External-ID": restaurant_guid,
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json"
                }
                
                # Get today's date in YYYYMMDD format
                today = datetime.datetime.now().strftime("%Y%m%d")
                
                # Create request parameters
                params = {
                    "businessDate": today,
                    "page": "0",
                    "pageSize": "1"  # Only get one record to test
                }
                
                # Make the API request
                test_url = f"{api_base_url}/orders/v2/ordersBulk"
                print(f"Testing API call to: {test_url}")
                print(f"With parameters: {params}")
                print(f"With headers: Authorization: Bearer {access_token[:10]}...")
                
                api_response = requests.get(
                    test_url,
                    headers=api_headers,
                    params=params
                )
                
                print(f"API response status: {api_response.status_code}")
                
                if api_response.status_code == 200:
                    print("API call SUCCESS!")
                    try:
                        data = api_response.json()
                        data_keys = data.keys() if isinstance(data, dict) else ["array_items"]
                        print(f"API response contains keys: {', '.join(data_keys)}")
                        print(f"API response: {json.dumps(data, indent=2)[:500]}...")
                        print("\nYour authentication and API access are working correctly!")
                        return True
                    except json.JSONDecodeError:
                        print("API response is not valid JSON.")
                        print(f"Raw response: {api_response.text[:500]}...")
                        return False
                else:
                    print("API call FAILED.")
                    print(f"Error response: {api_response.text[:500]}")
                    print("\nYour authentication is working, but the API call failed.")
                    print("This might be due to incorrect parameters or permissions.")
                    return False
            else:
                print("ERROR: Authentication response didn't contain a token.")
                print(f"Full response: {auth_data}")
                return False
        else:
            print("Authentication FAILED!")
            print(f"Error response: {response.text}")
            return False
            
    except Exception as e:
        print(f"ERROR during authentication request: {str(e)}")
        print(f"Exception type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_auth()
    sys.exit(0 if success else 1) 