#!/usr/bin/env python3
"""
Debug script to run tips processing directly without the Flask server
This helps isolate issues with the get_tips.py execution
"""

import os
import sys
import json
import subprocess
import tempfile
from datetime import datetime

def run_get_tips_directly():
    """Run get_tips.py directly to test if it works"""
    print("Testing get_tips.py directly...")
    
    # Set environment variable
    os.environ['TOAST_LOCATION_INDEX'] = '1'
    
    # Create a temporary file for output
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as temp_file:
        temp_filename = temp_file.name
    
    try:
        # Run get_tips.py with the same parameters the server would use
        cmd = [
            sys.executable,
            'get_tips.py',
            '--dates', '2025-06-13', '2025-06-15',
            '--output-file', temp_filename,
            '--response-webhook-url', 'https://fynch.app.n8n.cloud/webhook/0fc2febe-0f69-481b-bce0-40acd269e206'
        ]
        
        print(f"Running command: {' '.join(cmd)}")
        print(f"Environment TOAST_LOCATION_INDEX: {os.environ.get('TOAST_LOCATION_INDEX')}")
        
        # Run the command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        
        print(f"\nReturn code: {result.returncode}")
        print(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            print(f"STDERR:\n{result.stderr}")
        
        # Check if output file was created
        if os.path.exists(temp_filename):
            with open(temp_filename, 'r') as f:
                data = json.load(f)
                print(f"\nOutput file created successfully!")
                print(f"Summary: {data.get('summary', {})}")
        else:
            print("\nNo output file was created")
            
    except subprocess.TimeoutExpired:
        print("❌ Process timed out after 5 minutes")
    except Exception as e:
        print(f"❌ Error running get_tips.py: {e}")
    finally:
        # Clean up temp file
        if os.path.exists(temp_filename):
            os.unlink(temp_filename)

def check_dependencies():
    """Check if all required dependencies are available"""
    print("Checking dependencies...")
    
    required_files = [
        'get_tips.py',
        'config.py', 
        'toast_client.py'
    ]
    
    for file in required_files:
        if os.path.exists(file):
            print(f"✅ {file} exists")
        else:
            print(f"❌ {file} missing")
    
    # Check if we can import required modules
    try:
        import requests
        print("✅ requests module available")
    except ImportError:
        print("❌ requests module missing")
    
    try:
        from toast_client import ToastAPIClient
        print("✅ ToastAPIClient can be imported")
    except ImportError as e:
        print(f"❌ ToastAPIClient import failed: {e}")

def main():
    print("=" * 60)
    print("Debug Script for Tips Processing")
    print("=" * 60)
    
    check_dependencies()
    print("\n" + "=" * 60)
    run_get_tips_directly()

if __name__ == "__main__":
    main()