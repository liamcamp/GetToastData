from flask import Flask, request, jsonify
import json
import sys
import os
import threading
import uuid
import traceback
import logging
import requests
from datetime import datetime
from queue import Queue
from typing import Dict

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("server.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("toast-server")

app = Flask(__name__)

# Error webhook URL
ERROR_WEBHOOK_URL = "https://fynch.app.n8n.cloud/webhook/358766dc-09ae-4549-b762-f7079c0ac922"

# Store for background tasks
tasks: Dict[str, Dict] = {}
task_results: Dict[str, Dict] = {}

def send_error_to_webhook(error_msg: str, error_traceback: str, context: str = "server"):
    """Send error details to webhook"""
    try:
        payload = {
            "error": error_msg,
            "traceback": error_traceback,
            "context": context,
            "timestamp": datetime.utcnow().isoformat(),
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

def process_orders(task_id: str, params: Dict):
    """Process orders in background thread"""
    try:
        logger.info(f"Starting task {task_id} with params: {params}")
        
        # Set up environment and arguments
        os.environ['TOAST_LOCATION_INDEX'] = str(params['location_index'])
        logger.info(f"Setting location index to {params['location_index']}")
        
        # Import get_orders after setting environment variable
        import get_orders
        
        # Set up sys.argv for get_orders
        sys.argv = ['get_orders.py']
        if params['start_date'] and params['end_date']:
            sys.argv.extend(['--dates', params['start_date'], params['end_date']])
        if params['process']:
            sys.argv.append('--process')
        if params['webhook']:
            sys.argv.append('--webhook')
            # If a custom webhook URL is provided, pass it as well
            if params.get('webhook_url'):
                sys.argv.extend(['--webhook-url', params['webhook_url']])
            
        logger.info(f"Running get_orders.main() with args: {sys.argv}")
        
        # Run the main function
        get_orders.main()
        
        logger.info(f"Task {task_id} completed successfully")
        
        # Store success result
        task_results[task_id] = {
            'status': 'completed',
            'message': 'Orders processing completed successfully',
            'parameters': params,
            'completed_at': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        logger.error(f"Error in task {task_id}: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        # Send error to webhook
        send_error_to_webhook(
            error_msg=error_msg,
            error_traceback=error_traceback,
            context=f"task_{task_id}"
        )
        
        # Store error result
        task_results[task_id] = {
            'status': 'failed',
            'error': error_msg,
            'traceback': error_traceback,
            'parameters': params,
            'failed_at': datetime.utcnow().isoformat()
        }
    
    # Clean up task
    if task_id in tasks:
        del tasks[task_id]
        logger.info(f"Task {task_id} cleaned up")

@app.route('/run', methods=['POST'])
def run_orders():
    try:
        # Get JSON payload
        data = request.get_json()
        
        # Extract parameters
        start_date = data.get('startDate')
        end_date = data.get('endDate')
        process = data.get('process', False)
        webhook = data.get('webhook', False)
        location_index = data.get('locationIndex', 1)  # Default to 1 if not provided
        
        # Handle webhook parameter - can be boolean or string URL
        webhook_url = None
        if webhook:
            if isinstance(webhook, str):
                # If webhook is a string, it's a custom URL
                webhook_url = webhook
                webhook_enabled = True
            else:
                # If webhook is boolean True, use default URL
                webhook_enabled = bool(webhook)
        else:
            webhook_enabled = False
        
        # Validate dates
        if not start_date or not end_date:
            return jsonify({
                'error': 'Missing required parameters: startDate and endDate'
            }), 400
            
        # Validate location index
        try:
            location_index = int(location_index)
            if location_index < 1 or location_index > 5:
                return jsonify({
                    'error': 'locationIndex must be between 1 and 5'
                }), 400
        except (TypeError, ValueError):
            return jsonify({
                'error': 'locationIndex must be a valid integer between 1 and 5'
            }), 400
        
        # Generate task ID
        task_id = str(uuid.uuid4())
        
        # Store parameters
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'process': process,
            'webhook': webhook_enabled,
            'webhook_url': webhook_url,
            'location_index': location_index
        }
        
        # Create and start background thread
        thread = threading.Thread(
            target=process_orders,
            args=(task_id, params),
            daemon=True
        )
        tasks[task_id] = {
            'thread': thread,
            'started_at': datetime.utcnow().isoformat(),
            'parameters': params
        }
        thread.start()
        
        logger.info(f"Started task {task_id} with params {params}")
        
        # Return immediate response with task ID
        return jsonify({
            'status': 'processing',
            'message': 'Order processing started',
            'task_id': task_id,
            'parameters': params
        })
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        logger.error(f"Error in /run endpoint: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        # Send error to webhook
        send_error_to_webhook(
            error_msg=error_msg,
            error_traceback=error_traceback,
            context="run_endpoint"
        )
        
        return jsonify({
            'error': error_msg,
            'traceback': error_traceback
        }), 500

@app.route('/status/<task_id>', methods=['GET'])
def get_status(task_id):
    """Get the status of a processing task"""
    try:
        # Check if task is still running
        if task_id in tasks:
            return jsonify({
                'status': 'processing',
                'started_at': tasks[task_id]['started_at'],
                'parameters': tasks[task_id]['parameters']
            })
        
        # Check if task has completed
        if task_id in task_results:
            result = task_results[task_id]
            # Only clean up if the result is older than 5 minutes
            if 'completed_at' in result:
                completed_time = datetime.fromisoformat(result['completed_at'])
                if (datetime.utcnow() - completed_time).total_seconds() > 300:  # 5 minutes
                    del task_results[task_id]
            return jsonify(result)
        
        # Task not found
        return jsonify({
            'error': 'Task not found'
        }), 404
        
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        logger.error(f"Error in /status endpoint: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        # Send error to webhook
        send_error_to_webhook(
            error_msg=error_msg,
            error_traceback=error_traceback,
            context="status_endpoint"
        )
        
        return jsonify({
            'error': error_msg,
            'traceback': error_traceback
        }), 500

if __name__ == '__main__':
    try:
        logger.info("Starting Toast Orders API server on port 5000")
        app.run(host='0.0.0.0', port=5000)
    except Exception as e:
        error_msg = str(e)
        error_traceback = traceback.format_exc()
        logger.error(f"Failed to start server: {error_msg}")
        logger.error(f"Traceback: {error_traceback}")
        
        # Send error to webhook
        send_error_to_webhook(
            error_msg=error_msg,
            error_traceback=error_traceback,
            context="server_startup"
        ) 