#!/usr/bin/env python3
"""
Simplified Toast API Server with comprehensive logging and error handling
"""

import os
import sys
import json
import uuid
import time
import traceback
import logging
import requests
import threading
import subprocess
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify

# =============================================================================
# LOGGING SETUP - All logs go to one place with clear formatting
# =============================================================================

def setup_logging():
    """Set up comprehensive logging to both file and console"""
    
    # Create logs directory
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Main log file
    log_file = logs_dir / f"server_{datetime.now().strftime('%Y%m%d')}.log"
    
    # Configure root logger
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(name)-15s | %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Create logger for this module
    logger = logging.getLogger("toast-server")
    logger.info("=" * 80)
    logger.info("TOAST API SERVER STARTING")
    logger.info(f"Log file: {log_file}")
    logger.info(f"Working directory: {os.getcwd()}")
    logger.info(f"Python executable: {sys.executable}")
    logger.info("=" * 80)
    
    return logger

logger = setup_logging()
app = Flask(__name__)

# =============================================================================
# CONFIGURATION AND GLOBALS
# =============================================================================

# Store active tasks
active_tasks = {}
task_results = {}

# Error webhook for notifications
ERROR_WEBHOOK_URL = "https://fynch.app.n8n.cloud/webhook/358766dc-09ae-4549-b762-f7079c0ac922"

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def send_error_notification(error_msg: str, context: str = "server", traceback_str: str = None):
    """Send error notification to webhook"""
    try:
        payload = {
            "error": error_msg,
            "context": context,
            "timestamp": datetime.now().isoformat(),
            "server": "64.23.129.92",
            "traceback": traceback_str
        }
        
        response = requests.post(
            ERROR_WEBHOOK_URL,
            json=payload,
            timeout=10
        )
        logger.info(f"Error notification sent: {response.status_code}")
        return True
    except Exception as e:
        logger.error(f"Failed to send error notification: {e}")
        return False

def validate_request_data(data):
    """Validate incoming request data"""
    if not data:
        return False, "No JSON data provided"
    
    required_fields = ['startDate', 'endDate', 'webhook']
    missing_fields = [field for field in required_fields if not data.get(field)]
    
    if missing_fields:
        return False, f"Missing required fields: {', '.join(missing_fields)}"
    
    # Validate location index
    location_index = data.get('locationIndex', 1)
    try:
        location_index = int(location_index)
        if location_index < 1 or location_index > 5:
            return False, "locationIndex must be between 1 and 5"
    except (ValueError, TypeError):
        return False, "locationIndex must be a valid integer"
    
    return True, None

def run_get_tips_script(task_id: str, params: dict, synchronous: bool = False):
    """Run get_tips.py script in background or synchronously"""
    
    logger.info(f"Starting tips task {task_id} with params: {params}, synchronous: {synchronous}")
    
    try:
        # Set environment variable
        env = os.environ.copy()
        env['TOAST_LOCATION_INDEX'] = str(params['location_index'])
        
        # Build command
        cmd = [
            sys.executable,
            'functions/get_tips/get_tips.py',
            '--dates', params['start_date'], params['end_date']
        ]
        
        # Add synchronous flag if requested
        if synchronous:
            cmd.append('--synchronous')
        else:
            cmd.extend(['--response-webhook-url', params['webhook_url']])
        
        logger.info(f"Running command: {' '.join(cmd)}")
        logger.info(f"Environment TOAST_LOCATION_INDEX: {env.get('TOAST_LOCATION_INDEX')}")
        
        # Create log file for this task
        log_file = Path("logs") / f"task_{task_id}.log"
        
        # Run the command
        if synchronous:
            # For synchronous requests, capture stdout separately
            process = subprocess.run(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            # Write stderr to log file
            with open(log_file, 'w') as log_f:
                log_f.write(process.stderr)
            
            output = process.stderr
            stdout_output = process.stdout
        else:
            # For asynchronous requests, log everything to file
            with open(log_file, 'w') as log_f:
                process = subprocess.run(
                    cmd,
                    env=env,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    text=True,
                    timeout=600  # 10 minute timeout
                )
            
            # Read the log file to get output
            with open(log_file, 'r') as log_f:
                output = log_f.read()
            stdout_output = ""
        
        if process.returncode == 0:
            logger.info(f"Tips task {task_id} completed successfully")
            
            # For synchronous requests, parse the JSON output from stdout
            result_data = None
            if synchronous and stdout_output:
                try:
                    # Look for JSON output in stdout
                    lines = stdout_output.split('\n')
                    for line in lines:
                        if line.strip().startswith('{') and '"tips_by_date"' in line:
                            result_data = json.loads(line.strip())
                            break
                except json.JSONDecodeError:
                    logger.warning("Could not parse JSON from synchronous output")
            
            task_results[task_id] = {
                'status': 'completed',
                'message': 'Tips processing completed successfully',
                'output': output[-1000:],  # Last 1000 chars
                'log_file': str(log_file),
                'completed_at': datetime.now().isoformat(),
                'data': result_data  # Include parsed data for synchronous requests
            }
        else:
            logger.error(f"Tips task {task_id} failed with return code {process.returncode}")
            task_results[task_id] = {
                'status': 'failed',
                'error': f"Process failed with return code {process.returncode}",
                'output': output[-1000:],  # Last 1000 chars
                'log_file': str(log_file),
                'failed_at': datetime.now().isoformat()
            }
            
            # Send error notification
            send_error_notification(
                error_msg=f"Tips task {task_id} failed",
                context=f"get_tips_execution",
                traceback_str=output[-2000:]  # Last 2000 chars for context
            )
    
    except subprocess.TimeoutExpired:
        error_msg = f"Tips task {task_id} timed out after 10 minutes"
        logger.error(error_msg)
        task_results[task_id] = {
            'status': 'failed',
            'error': 'Process timed out',
            'failed_at': datetime.now().isoformat()
        }
        send_error_notification(error_msg, "timeout")
        
    except Exception as e:
        error_msg = f"Tips task {task_id} failed with exception: {str(e)}"
        error_trace = traceback.format_exc()
        logger.error(error_msg)
        logger.error(error_trace)
        
        task_results[task_id] = {
            'status': 'failed',
            'error': error_msg,
            'traceback': error_trace,
            'failed_at': datetime.now().isoformat()
        }
        
        send_error_notification(error_msg, "exception", error_trace)
    
    finally:
        # Clean up active task
        if task_id in active_tasks:
            del active_tasks[task_id]

def run_get_orders_script(task_id: str, params: dict):
    """Run get_orders.py script in background"""
    
    logger.info(f"Starting orders task {task_id} with params: {params}")
    
    try:
        # Set environment variable
        env = os.environ.copy()
        env['TOAST_LOCATION_INDEX'] = str(params['location_index'])
        
        # Build command for get_orders.py
        cmd = [sys.executable, 'functions/get_orders/get_orders.py']
        
        if params['start_date'] and params['end_date']:
            cmd.extend(['--dates', params['start_date'], params['end_date']])
        if params.get('process'):
            cmd.append('--process')
        if params.get('webhook'):
            cmd.append('--webhook')
            if params.get('webhook_url'):
                cmd.extend(['--webhook-url', params['webhook_url']])
        
        logger.info(f"Running command: {' '.join(cmd)}")
        logger.info(f"Environment TOAST_LOCATION_INDEX: {env.get('TOAST_LOCATION_INDEX')}")
        
        # Create log file for this task
        log_file = Path("logs") / f"task_{task_id}.log"
        
        # Run the command
        with open(log_file, 'w') as log_f:
            process = subprocess.run(
                cmd,
                env=env,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=600  # 10 minute timeout
            )
        
        # Read the log file to get output
        with open(log_file, 'r') as log_f:
            output = log_f.read()
        
        if process.returncode == 0:
            logger.info(f"Orders task {task_id} completed successfully")
            task_results[task_id] = {
                'status': 'completed',
                'message': 'Orders processing completed successfully',
                'output': output[-1000:],  # Last 1000 chars
                'log_file': str(log_file),
                'completed_at': datetime.now().isoformat()
            }
        else:
            logger.error(f"Orders task {task_id} failed with return code {process.returncode}")
            task_results[task_id] = {
                'status': 'failed',
                'error': f"Process failed with return code {process.returncode}",
                'output': output[-1000:],  # Last 1000 chars
                'log_file': str(log_file),
                'failed_at': datetime.now().isoformat()
            }
            
            # Send error notification
            send_error_notification(
                error_msg=f"Orders task {task_id} failed",
                context=f"get_orders_execution",
                traceback_str=output[-2000:]  # Last 2000 chars for context
            )
    
    except subprocess.TimeoutExpired:
        error_msg = f"Orders task {task_id} timed out after 10 minutes"
        logger.error(error_msg)
        task_results[task_id] = {
            'status': 'failed',
            'error': 'Process timed out',
            'failed_at': datetime.now().isoformat()
        }
        send_error_notification(error_msg, "timeout")
        
    except Exception as e:
        error_msg = f"Orders task {task_id} failed with exception: {str(e)}"
        error_trace = traceback.format_exc()
        logger.error(error_msg)
        logger.error(error_trace)
        
        task_results[task_id] = {
            'status': 'failed',
            'error': error_msg,
            'traceback': error_trace,
            'failed_at': datetime.now().isoformat()
        }
        
        send_error_notification(error_msg, "exception", error_trace)
    
    finally:
        # Clean up active task
        if task_id in active_tasks:
            del active_tasks[task_id]

# =============================================================================
# FLASK ROUTES
# =============================================================================

@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'active_tasks': len(active_tasks),
        'completed_tasks': len(task_results)
    })

@app.route('/tips', methods=['POST'])
def process_tips():
    """Process tips data"""
    
    request_start = time.time()
    client_ip = request.remote_addr
    
    logger.info(f"Received /tips request from {client_ip}")
    
    try:
        # Get and validate request data
        data = request.get_json()
        logger.info(f"Request data: {json.dumps(data, indent=2)}")
        
        # Check if synchronous request
        is_synchronous = data.get('synchronous', False)
        
        # For synchronous requests, webhook is not required
        if is_synchronous:
            required_fields = ['startDate', 'endDate']
        else:
            required_fields = ['startDate', 'endDate', 'webhook']
        
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            error_msg = f"Missing required fields: {', '.join(missing_fields)}"
            logger.warning(f"Invalid request: {error_msg}")
            return jsonify({'error': error_msg}), 400
        
        # Validate location index
        location_index = data.get('locationIndex', 1)
        try:
            location_index = int(location_index)
            if location_index < 1 or location_index > 5:
                return jsonify({'error': 'locationIndex must be between 1 and 5'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'locationIndex must be a valid integer'}), 400
        
        # Extract parameters
        params = {
            'start_date': data['startDate'],
            'end_date': data['endDate'],
            'webhook_url': data.get('webhook', ''),
            'location_index': location_index
        }
        
        # Generate task ID
        task_id = str(uuid.uuid4())
        
        # Store task info
        active_tasks[task_id] = {
            'params': params,
            'started_at': datetime.now().isoformat(),
            'client_ip': client_ip,
            'type': 'tips',
            'synchronous': is_synchronous
        }
        
        if is_synchronous:
            # Handle synchronous request - run in the current thread
            logger.info(f"Processing synchronous tips request {task_id}")
            
            # Run the script synchronously
            run_get_tips_script(task_id, params, synchronous=True)
            
            # Get the result
            if task_id in task_results:
                result = task_results[task_id]
                if result['status'] == 'completed' and result.get('data'):
                    # Return the tips data directly
                    request_time = (time.time() - request_start) * 1000
                    logger.info(f"Synchronous task {task_id} completed in {request_time:.1f}ms")
                    return jsonify(result['data'])
                else:
                    # Return error if failed
                    return jsonify({
                        'error': result.get('error', 'Unknown error'),
                        'task_id': task_id,
                        'output': result.get('output', '')
                    }), 500
            else:
                return jsonify({
                    'error': 'Task result not found',
                    'task_id': task_id
                }), 500
        else:
            # Handle asynchronous request - run in background thread
            thread = threading.Thread(
                target=run_get_tips_script,
                args=(task_id, params, False),
                daemon=True
            )
            thread.start()
            
            request_time = (time.time() - request_start) * 1000
            logger.info(f"Task {task_id} started successfully in {request_time:.1f}ms")
            
            return jsonify({
                'status': 'processing',
                'task_id': task_id,
                'message': 'Tips processing started',
                'params': params
            })
        
    except Exception as e:
        error_msg = f"Error in /tips endpoint: {str(e)}"
        error_trace = traceback.format_exc()
        logger.error(error_msg)
        logger.error(error_trace)
        
        send_error_notification(error_msg, "tips_endpoint", error_trace)
        
        return jsonify({
            'error': error_msg,
            'traceback': error_trace
        }), 500

@app.route('/orders', methods=['POST'])
def process_orders():
    """Process orders data (replaces old /run endpoint)"""
    
    request_start = time.time()
    client_ip = request.remote_addr
    
    logger.info(f"Received /orders request from {client_ip}")
    
    try:
        # Get and validate request data
        data = request.get_json()
        logger.info(f"Request data: {json.dumps(data, indent=2)}")
        
        # Extract parameters (similar to old /run endpoint)
        start_date = data.get('startDate')
        end_date = data.get('endDate')
        process_flag = data.get('process', False)
        webhook = data.get('webhook', False)
        location_index = data.get('locationIndex', 1)
        
        # Validate required fields
        if not start_date or not end_date:
            return jsonify({'error': 'Missing required parameters: startDate and endDate'}), 400
        
        # Validate location index
        try:
            location_index = int(location_index)
            if location_index < 1 or location_index > 5:
                return jsonify({'error': 'locationIndex must be between 1 and 5'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': 'locationIndex must be a valid integer'}), 400
        
        # Handle webhook parameter - can be boolean or string URL
        webhook_url = None
        webhook_enabled = False
        if webhook:
            if isinstance(webhook, str):
                # If webhook is a string, it's a custom URL
                webhook_url = webhook
                webhook_enabled = True
            else:
                # If webhook is boolean True, use default behavior
                webhook_enabled = bool(webhook)
        
        # Build parameters
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'process': process_flag,
            'webhook': webhook_enabled,
            'webhook_url': webhook_url,
            'location_index': location_index
        }
        
        # Generate task ID
        task_id = str(uuid.uuid4())
        
        # Store task info
        active_tasks[task_id] = {
            'params': params,
            'started_at': datetime.now().isoformat(),
            'client_ip': client_ip,
            'type': 'orders'
        }
        
        # Start background thread
        thread = threading.Thread(
            target=run_get_orders_script,
            args=(task_id, params),
            daemon=True
        )
        thread.start()
        
        request_time = (time.time() - request_start) * 1000
        logger.info(f"Orders task {task_id} started successfully in {request_time:.1f}ms")
        
        return jsonify({
            'status': 'processing',
            'task_id': task_id,
            'message': 'Order processing started',
            'params': params
        })
        
    except Exception as e:
        error_msg = f"Error in /orders endpoint: {str(e)}"
        error_trace = traceback.format_exc()
        logger.error(error_msg)
        logger.error(error_trace)
        
        send_error_notification(error_msg, "orders_endpoint", error_trace)
        
        return jsonify({
            'error': error_msg,
            'traceback': error_trace
        }), 500

@app.route('/status/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """Get status of a task"""
    
    logger.info(f"Status check for task {task_id}")
    
    try:
        # Check if task is still active
        if task_id in active_tasks:
            task_info = active_tasks[task_id]
            return jsonify({
                'status': 'processing',
                'task_id': task_id,
                'started_at': task_info['started_at'],
                'params': task_info['params']
            })
        
        # Check if task is completed
        if task_id in task_results:
            result = task_results[task_id]
            return jsonify({
                'task_id': task_id,
                **result
            })
        
        # Task not found
        return jsonify({
            'error': 'Task not found',
            'task_id': task_id
        }), 404
        
    except Exception as e:
        error_msg = f"Error checking status: {str(e)}"
        logger.error(error_msg)
        return jsonify({'error': error_msg}), 500

@app.route('/logs/<task_id>', methods=['GET'])
def get_task_logs(task_id):
    """Get logs for a specific task"""
    
    try:
        log_file = Path("logs") / f"task_{task_id}.log"
        
        if not log_file.exists():
            return jsonify({'error': 'Log file not found'}), 404
        
        with open(log_file, 'r') as f:
            logs = f.read()
        
        return jsonify({
            'task_id': task_id,
            'logs': logs,
            'log_file': str(log_file)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/debug', methods=['GET'])
def debug_info():
    """Get debug information about the server"""
    
    return jsonify({
        'server_info': {
            'working_directory': os.getcwd(),
            'python_executable': sys.executable,
            'python_version': sys.version,
            'environment_vars': {
                'TOAST_LOCATION_INDEX': os.getenv('TOAST_LOCATION_INDEX'),
                'TOAST_CLIENT_ID': os.getenv('TOAST_CLIENT_ID')[:10] + '...' if os.getenv('TOAST_CLIENT_ID') else None
            }
        },
        'tasks': {
            'active': len(active_tasks),
            'completed': len(task_results),
            'active_task_ids': list(active_tasks.keys()),
            'completed_task_ids': list(task_results.keys())
        },
        'files': {
            'get_tips_exists': os.path.exists('functions/get_tips/get_tips.py'),
            'get_orders_exists': os.path.exists('functions/get_orders/get_orders.py'),
            'config_exists': os.path.exists('config/config.py'),
            'toast_client_exists': os.path.exists('server/toast_client.py')
        }
    })

# =============================================================================
# SERVER STARTUP
# =============================================================================

if __name__ == '__main__':
    try:
        # Check required files exist
        required_files = [
            'functions/get_tips/get_tips.py',
            'functions/get_orders/get_orders.py', 
            'config/config.py',
            'server/toast_client.py'
        ]
        missing_files = [f for f in required_files if not os.path.exists(f)]
        
        if missing_files:
            error_msg = f"Missing required files: {', '.join(missing_files)}"
            logger.error(error_msg)
            send_error_notification(error_msg, "startup")
            sys.exit(1)
        
        logger.info("Starting Flask server on 0.0.0.0:5000")
        logger.info("Available endpoints:")
        logger.info("  POST /tips         - Process tips data")
        logger.info("  POST /orders       - Process orders data (replaces /run)")
        logger.info("  GET  /status/<id>  - Check task status")
        logger.info("  GET  /logs/<id>    - View task logs")
        logger.info("  GET  /health       - Health check")
        logger.info("  GET  /debug        - Debug information")
        
        # Try port 5000, fallback to 5001 if busy
        port = 5000
        try:
            app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
        except OSError as e:
            if "Address already in use" in str(e):
                logger.warning(f"Port {port} is busy, trying port 5001")
                port = 5001
                app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
            else:
                raise
        
    except Exception as e:
        error_msg = f"Failed to start server: {str(e)}"
        error_trace = traceback.format_exc()
        logger.error(error_msg)
        logger.error(error_trace)
        send_error_notification(error_msg, "startup", error_trace)
        sys.exit(1)