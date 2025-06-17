#!/usr/bin/env python3
"""
Test script to demonstrate the custom webhook URL feature

This script shows how to use the updated /run endpoint with a custom webhook URL.
"""

import requests
import json

# Server endpoint
SERVER_URL = "http://64.23.129.92:5000/run"

# Example 1: Using the default webhook
print("Example 1: Using default webhook")
payload_default = {
    "startDate": "2025-01-07",
    "endDate": "2025-01-07",
    "process": True,
    "webhook": True,  # Boolean True uses default webhook
    "locationIndex": 4
}

print(f"Payload: {json.dumps(payload_default, indent=2)}")

# Example 2: Using a custom webhook URL
print("\nExample 2: Using custom webhook URL")
payload_custom = {
    "startDate": "2025-01-07",
    "endDate": "2025-01-07",
    "process": True,
    "webhook": "https://example.com/my-custom-webhook",  # String URL for custom webhook
    "locationIndex": 4
}

print(f"Payload: {json.dumps(payload_custom, indent=2)}")

# Example 3: No webhook (just process data)
print("\nExample 3: No webhook")
payload_no_webhook = {
    "startDate": "2025-01-07",
    "endDate": "2025-01-07",
    "process": True,
    "webhook": False,  # No webhook
    "locationIndex": 4
}

print(f"Payload: {json.dumps(payload_no_webhook, indent=2)}")

# To send the request (uncomment to test):
# response = requests.post(SERVER_URL, json=payload_custom)
# print(f"Response: {response.status_code}")
# print(f"Response body: {response.json()}") 