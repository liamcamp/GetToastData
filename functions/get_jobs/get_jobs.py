#!/usr/bin/env python3
"""
Toast Jobs API Script - Job Information Retrieval

This script allows you to retrieve job information from the Toast Jobs API.
The script requires valid Toast API credentials and appropriate permissions to access job data.

Prerequisites:
1. Valid Toast API credentials (client ID and client secret) configured in config.py
2. Restaurant GUID configured in config.py
3. Appropriate permissions to access job data in Toast

Usage examples:
- Fetch all jobs: python get_jobs.py
- Fetch jobs by ID: python get_jobs.py --job-ids job1,job2,job3
- Save results to a file: python get_jobs.py --output-file jobs.json
"""

import os
import sys
import argparse
import json
import datetime
import logging
import traceback
from typing import Dict, Any, Optional

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "get_jobs.log")),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("toast-jobs")

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Fetch job data from Toast API')
    
    parser.add_argument('--job-ids', help='Comma-separated list of job IDs to retrieve (optional - if not provided, fetches all jobs)')
    parser.add_argument('--location-index', type=int, choices=range(1, 6),
                       help='Location index (1-5) to determine which restaurant GUID to use')
    parser.add_argument('--output-file', dest='output', help='Optional file to save job data')
    parser.add_argument('--debug', action='store_true', help='Enable detailed debugging output')
    
    args = parser.parse_args()
    
    # Set location index in environment if provided and not already set
    if args.location_index and not os.getenv('TOAST_LOCATION_INDEX'):
        os.environ['TOAST_LOCATION_INDEX'] = str(args.location_index)
        logger.info(f"Setting location index to {args.location_index}")
    
    return args

# Parse arguments and set location index before importing other modules
args = parse_args()

# Try to import ToastAPIClient from toast_client.py
try:
    # Add the project root to the path
    sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
    from server.toast_client import ToastAPIClient
except ImportError as e:
    logger.error(f"Failed to import ToastAPIClient: {str(e)}")
    raise

def main():
    """Main function to run the script"""
    args = parse_args()
    
    logger.info("=" * 80)
    logger.info(f"Toast Jobs API Script - Started at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 80)
    
    try:
        # Get location index from environment if set via command line
        location_index = None
        if 'TOAST_LOCATION_INDEX' in os.environ:
            try:
                location_index = int(os.environ['TOAST_LOCATION_INDEX'])
                logger.info(f"Using location index from environment: {location_index}")
            except ValueError:
                logger.warning("Invalid TOAST_LOCATION_INDEX in environment, defaulting to location index 4")
                location_index = 4
                os.environ['TOAST_LOCATION_INDEX'] = str(location_index)
        
        # If location_index is still None, default to 4
        if location_index is None:
            logger.info("No location index specified, defaulting to location index 4")
            location_index = 4
            os.environ['TOAST_LOCATION_INDEX'] = str(location_index)
                
        # Force reload of config.py to get new GUID based on environment variable
        if location_index is not None:
            # Set environment variable to ensure config.py picks it up
            os.environ['TOAST_LOCATION_INDEX'] = str(location_index)
            logger.info(f"Explicitly setting TOAST_LOCATION_INDEX to {location_index} before client initialization")
            
            # Force unload of config module if it's already been imported
            import sys
            if 'config' in sys.modules:
                logger.info("Removing config module from sys.modules to force fresh import")
                del sys.modules['config']
        
        # Initialize the client - this will now use the updated config
        logger.info("Initializing Toast API client...")
        client = ToastAPIClient()
        
        # Double-check which restaurant GUID is being used
        try:
            import config.config as config
            logger.info(f"Using restaurant GUID: {config.TOAST_RESTAURANT_GUID} for location index {location_index}")
        except ImportError:
            logger.warning("Could not import config to verify restaurant GUID")
        
        if args.job_ids:
            logger.info(f"Fetching job data for IDs: {args.job_ids}")
        else:
            logger.info("Fetching all jobs")
        
        # Try to fetch job data
        try:
            jobs_response = client.get_jobs(args.job_ids)
        except Exception as e:
            logger.error(f"Jobs API call failed: {e}")
            
            # Let's also try some other endpoints to see what we can access
            logger.info("\n" + "=" * 80)
            logger.info("TESTING OTHER ENDPOINTS FOR COMPARISON")
            logger.info("=" * 80)
            
            # Test orders endpoint (we know this works)
            try:
                logger.info("Testing orders endpoint...")
                today = datetime.datetime.now().strftime("%Y-%m-%d")
                start_date = f"{today}T00:00:00.000Z"
                end_date = f"{today}T23:59:59.999Z"
                orders_response = client.get_orders(start_date, end_date)
                logger.info("✓ Orders endpoint accessible")
            except Exception as orders_e:
                logger.error(f"✗ Orders endpoint failed: {orders_e}")
            
            # Test menus endpoint
            try:
                logger.info("Testing menus endpoint...")
                menus_response = client.get_menus()
                logger.info("✓ Menus endpoint accessible")
            except Exception as menus_e:
                logger.error(f"✗ Menus endpoint failed: {menus_e}")
            
            logger.info("=" * 80)
            
            # Re-raise the original jobs API error
            raise
        
        # Display the job information
        logger.info("\n" + "=" * 80)
        if args.job_ids:
            logger.info("JOB INFORMATION (FILTERED)")
        else:
            logger.info("ALL JOBS INFORMATION")
        logger.info("=" * 80)
        
        if isinstance(jobs_response, list):
            if len(jobs_response) == 0:
                logger.info("No jobs found")
            else:
                logger.info(f"Found {len(jobs_response)} job(s)")
                for i, job in enumerate(jobs_response):
                    logger.info(f"\n--- Job {i+1} ---")
                    if isinstance(job, dict):
                        for key, value in job.items():
                            logger.info(f"{key}: {value}")
                    else:
                        logger.info(f"Job data: {job}")
        elif isinstance(jobs_response, dict):
            # Single job or response wrapper
            if 'jobs' in jobs_response:
                jobs = jobs_response['jobs']
                logger.info(f"Found {len(jobs)} job(s)")
                for i, job in enumerate(jobs):
                    logger.info(f"\n--- Job {i+1} ---")
                    if isinstance(job, dict):
                        for key, value in job.items():
                            logger.info(f"{key}: {value}")
                    else:
                        logger.info(f"Job data: {job}")
            else:
                # Single job
                for key, value in jobs_response.items():
                    logger.info(f"{key}: {value}")
        else:
            logger.error("Unexpected response format from jobs API")
            logger.info(f"Job data: {jobs_response}")
        
        logger.info("=" * 80)
        
        # If debug mode is enabled, show the raw response
        if args.debug:
            logger.info("\n" + "=" * 80)
            logger.info("RAW API RESPONSE")
            logger.info("=" * 80)
            logger.info(json.dumps(jobs_response, indent=2))
            logger.info("=" * 80)
        
        # Save data if output specified
        if args.output:
            try:
                with open(args.output, 'w') as f:
                    json.dump(jobs_response, f, indent=2)
                logger.info(f"Job data saved to {args.output}")
            except Exception as e:
                logger.error(f"Error saving to output file: {str(e)}")
                raise
        
        logger.info("Operation completed successfully.")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        logger.error("=" * 80)
        sys.exit(1)

if __name__ == "__main__":
    main()