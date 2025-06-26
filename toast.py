#!/usr/bin/env python3
"""
Toast API Functions Router
A single script to call any Toast API function from the main directory.

Usage:
    python3 toast.py get_employee [args...]
    python3 toast.py get_orders [args...]
    python3 toast.py get_time_entries [args...]
    python3 toast.py get_tips [args...]
    python3 toast.py get_jobs [args...]

Examples:
    python3 toast.py get_orders --location-index 1 --dates 2025-06-19 2025-06-19
    python3 toast.py get_time_entries --location-index 1 --dates 2025-06-19 2025-06-19
    python3 toast.py get_tips --location-index 1 --date 2025-06-19 --output-file tips.json
    python3 toast.py get_employee --location-index 1
    python3 toast.py get_jobs --location-index 1 --output-file jobs.json
"""

import os
import sys
import subprocess

def main():
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Expect function name as first argument
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)
    
    function_name = sys.argv[1]
    if function_name not in ['get_employee', 'get_orders', 'get_time_entries', 'get_tips', 'get_jobs']:
        print(f"Error: Unknown function '{function_name}'")
        print_usage()
        sys.exit(1)
    
    # Remove the function name from arguments
    args = sys.argv[2:]
    script_file = f"{function_name}.py"
    
    # Path to the actual script
    actual_script = os.path.join(script_dir, 'functions', function_name, script_file)
    
    # Check if the actual script exists
    if not os.path.exists(actual_script):
        print(f"Error: Could not find {actual_script}")
        sys.exit(1)
    
    # Execute the actual script
    cmd = [sys.executable, actual_script] + args
    
    try:
        result = subprocess.run(cmd, cwd=script_dir)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Error executing script: {e}")
        sys.exit(1)

def print_usage():
    print(__doc__)

if __name__ == "__main__":
    main()