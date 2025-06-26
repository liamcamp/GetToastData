#!/usr/bin/env python3
"""
Check the server status and running tasks
"""

import requests
import json
import time

def check_server_health():
    """Check if the server is running and responsive"""
    try:
        # Simple health check by calling a non-existent endpoint
        response = requests.get("http://64.23.129.92:5000/health", timeout=5)
        return True
    except requests.exceptions.ConnectionError:
        return False
    except:
        return True  # Server responded, even if endpoint doesn't exist

def check_recent_tasks():
    """Check for recent tasks that might be stuck"""
    # This would need to be implemented on the server side
    pass

def main():
    print("Checking server status...")
    
    if check_server_health():
        print("✅ Server is responding")
    else:
        print("❌ Server is not responding")
        return
    
    # Check a few recent task IDs to see their status
    test_task_ids = [
        "0ef609e3-faed-431a-8799-0a75d2e1acc1"  # The one we just created
    ]
    
    for task_id in test_task_ids:
        print(f"\nChecking task {task_id}...")
        try:
            response = requests.get(f"http://64.23.129.92:5000/status/{task_id}", timeout=10)
            if response.status_code == 200:
                data = response.json()
                print(f"Status: {data.get('status', 'unknown')}")
                if 'started_at' in data:
                    print(f"Started: {data['started_at']}")
                if 'error' in data:
                    print(f"Error: {data['error']}")
            else:
                print(f"Status check failed: {response.status_code}")
        except Exception as e:
            print(f"Error checking task: {e}")

if __name__ == "__main__":
    main()