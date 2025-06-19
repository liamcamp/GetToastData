#!/usr/bin/env python3
"""
Test script for the /tips endpoint
"""

import requests
import json

def test_tips_endpoint():
    """Test the /tips endpoint with the provided payload"""
    
    url = "http://64.23.129.92:5000/tips"
    payload = {
        "startDate": "2025-06-13",
        "endDate": "2025-06-15", 
        "webhook": "https://fynch.app.n8n.cloud/webhook/0fc2febe-0f69-481b-bce0-40acd269e206",
        "locationIndex": 1
    }
    
    print(f"Testing endpoint: {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        # Make the request
        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30
        )
        
        print(f"\nResponse Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        print(f"Response Body: {response.text}")
        
        if response.status_code == 200:
            print("\n✅ Request successful!")
            try:
                response_data = response.json()
                if 'task_id' in response_data:
                    print(f"Task ID: {response_data['task_id']}")
                    return response_data['task_id']
            except json.JSONDecodeError:
                print("Response is not valid JSON")
        else:
            print(f"\n❌ Request failed with status {response.status_code}")
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection failed - server may not be running or accessible")
    except requests.exceptions.Timeout:
        print("❌ Request timed out")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    
    return None

def test_status_endpoint(task_id):
    """Test the status endpoint with a task ID"""
    if not task_id:
        return
        
    url = f"http://64.23.129.92:5000/status/{task_id}"
    print(f"\nTesting status endpoint: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        print(f"Status Response: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Status check failed: {e}")

if __name__ == "__main__":
    print("Testing /tips endpoint...")
    task_id = test_tips_endpoint()
    test_status_endpoint(task_id)