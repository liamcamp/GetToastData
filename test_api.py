#!/usr/bin/env python3
"""
Simple API test script for the Toast API server
Usage: python test_api.py [server_url]
"""

import sys
import json
import time
import requests
from datetime import datetime

def test_server(base_url="http://64.23.129.92:5000"):
    """Test the server endpoints"""
    
    print(f"🧪 Testing Toast API Server: {base_url}")
    print("=" * 60)
    
    # Test 1: Health check
    print("1️⃣ Health Check...")
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Health check passed")
            print(f"   📊 Active tasks: {data.get('active_tasks', 0)}")
            print(f"   📊 Completed tasks: {data.get('completed_tasks', 0)}")
        else:
            print(f"   ❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Health check failed: {e}")
        return False
    
    print()
    
    # Test 2: Debug info
    print("2️⃣ Debug Info...")
    try:
        response = requests.get(f"{base_url}/debug", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Debug info retrieved")
            print(f"   📁 Working dir: {data['server_info']['working_directory']}")
            print(f"   🐍 Python: {data['server_info']['python_version'].split()[0]}")
            print(f"   📄 Required files: {all(data['files'].values())}")
        else:
            print(f"   ⚠️ Debug info failed: {response.status_code}")
    except Exception as e:
        print(f"   ⚠️ Debug info failed: {e}")
    
    print()
    
    # Test 3: Tips endpoint
    print("3️⃣ Tips Processing...")
    
    payload = {
        "startDate": "2025-06-13",
        "endDate": "2025-06-15",
        "webhook": "https://fynch.app.n8n.cloud/webhook/0fc2febe-0f69-481b-bce0-40acd269e206",
        "locationIndex": 1
    }
    
    try:
        print(f"   📤 Sending request...")
        print(f"   📋 Payload: {json.dumps(payload, indent=6)}")
        
        response = requests.post(
            f"{base_url}/tips",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            task_id = data.get('task_id')
            print(f"   ✅ Request accepted")
            print(f"   🆔 Task ID: {task_id}")
            
            # Test 4: Status checking
            print()
            print("4️⃣ Status Monitoring...")
            
            for i in range(12):  # Check for up to 2 minutes
                try:
                    status_response = requests.get(f"{base_url}/status/{task_id}", timeout=10)
                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        status = status_data.get('status', 'unknown')
                        
                        print(f"   📊 Check {i+1}: Status = {status}")
                        
                        if status == 'completed':
                            print(f"   ✅ Task completed successfully!")
                            if 'output' in status_data:
                                print(f"   📄 Output preview: {status_data['output'][:200]}...")
                            break
                        elif status == 'failed':
                            print(f"   ❌ Task failed: {status_data.get('error', 'Unknown error')}")
                            
                            # Try to get logs
                            try:
                                logs_response = requests.get(f"{base_url}/logs/{task_id}", timeout=10)
                                if logs_response.status_code == 200:
                                    logs_data = logs_response.json()
                                    print(f"   📋 Error logs: ...{logs_data['logs'][-500:]}")
                            except:
                                pass
                            break
                        elif status == 'processing':
                            if i < 11:  # Don't sleep on last iteration
                                time.sleep(10)
                        else:
                            print(f"   ❓ Unknown status: {status}")
                            break
                    else:
                        print(f"   ❌ Status check failed: {status_response.status_code}")
                        break
                        
                except Exception as e:
                    print(f"   ❌ Status check error: {e}")
                    break
            else:
                print(f"   ⏰ Task still running after 2 minutes")
                
        else:
            print(f"   ❌ Request failed: {response.status_code}")
            print(f"   📄 Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"   ❌ Tips request failed: {e}")
        return False
    
    print()
    
    # Test 5: Orders endpoint (bonus test)
    print("5️⃣ Orders Endpoint Test (Quick)...")
    
    orders_payload = {
        "startDate": "2025-06-18",
        "endDate": "2025-06-18",
        "process": False,
        "webhook": False,
        "locationIndex": 1
    }
    
    try:
        print(f"   📤 Testing /orders endpoint...")
        response = requests.post(
            f"{base_url}/orders",
            json=orders_payload,
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Orders endpoint working")
            print(f"   🆔 Task ID: {data.get('task_id')}")
        else:
            print(f"   ⚠️ Orders endpoint returned: {response.status_code}")
    except Exception as e:
        print(f"   ⚠️ Orders endpoint test failed: {e}")
    
    print()
    print("🎉 Test completed!")
    return True

if __name__ == "__main__":
    # Allow custom server URL
    server_url = sys.argv[1] if len(sys.argv) > 1 else "http://64.23.129.92:5000"
    
    if server_url.startswith("local"):
        server_url = "http://localhost:5000"
    
    success = test_server(server_url)
    sys.exit(0 if success else 1)