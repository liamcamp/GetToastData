"""Toast API client for interacting with the Toast POS system."""
import requests
import time
import datetime
import urllib.parse
import json
import logging
import importlib
import sys
from typing import Dict, Any, Optional, List

# Set up logging
logger = logging.getLogger("toast-client")

class ToastAPIClient:
    """Client for interacting with the Toast API with automatic token management."""
    
    # Add retry configuration parameters
    MAX_RETRIES = 5
    INITIAL_BACKOFF_SECONDS = 1
    MAX_BACKOFF_SECONDS = 30
    
    def __init__(self):
        """Initialize the Toast API client with configuration."""
        # Force reload of config to get the latest values
        if 'config' in sys.modules:
            logger.info("Reloading config module to get latest configuration")
            importlib.reload(sys.modules['config'])
            
        # Import the config module (after potential reload)
        import config.config as config
        
        # Store configuration values from imported module
        self.base_url = config.TOAST_API_BASE_URL
        self.auth_url = config.TOAST_AUTH_URL
        self.restaurant_guid = config.TOAST_RESTAURANT_GUID
        self.client_id = config.TOAST_CLIENT_ID
        self.client_secret = config.TOAST_CLIENT_SECRET
        
        # Log the GUID being used
        logger.info(f"Initializing Toast API client with restaurant GUID: {self.restaurant_guid}")
        
        # Token management
        self.token = None
        self.token_expiry = None
        
        if not all([self.restaurant_guid, self.client_id, self.client_secret]):
            raise ValueError("Missing required Toast API credentials")
        
        # Get initial token
        self._refresh_token()
    
    def _refresh_token(self):
        """
        Get a new authentication token from the Toast API with retry logic.
        
        Raises:
            requests.exceptions.RequestException: If the authentication request fails after retries
        """
        logger.info("Attempting to fetch new authentication token from Toast API...")
        logger.info(f"Using auth URL: {self.auth_url}")
        
        payload = {
            "clientId": self.client_id,
            "clientSecret": self.client_secret,
            "userAccessType": "TOAST_MACHINE_CLIENT"
        }
        headers = {"Content-Type": "application/json"}
        
        current_retry = 0
        backoff_seconds = self.INITIAL_BACKOFF_SECONDS
        
        while current_retry <= self.MAX_RETRIES:
            try:
                logger.info(f"Authentication attempt {current_retry + 1}/{self.MAX_RETRIES + 1}. Payload: {json.dumps(payload, indent=2)}")
                
                response = requests.post(
                    self.auth_url,
                    json=payload,
                    headers=headers,
                    timeout=10 # Add a timeout for auth requests
                )
                
                logger.info(f"Auth response status: {response.status_code}")
                if response.status_code == 429:
                    logger.warning(f"Auth request received 429 (Too Many Requests). Retrying in {backoff_seconds}s...")
                    # Fall through to the retry sleep logic
                elif response.status_code != 200:
                    logger.error(f"Auth response error: {response.text}")
                    # For non-429 errors that are not successful, raise immediately or after a few retries if they could be transient
                    if current_retry >= 2: # Only retry a couple of times for non-429s here.
                         response.raise_for_status() # This will raise an HTTPError for bad status codes
                    # else, fall through to retry for other potentially transient server errors on auth
                else: # Success
                    auth_data = response.json()
                    logger.info(f"Auth token response keys: {', '.join(auth_data.keys())}")
                    # logger.info(f"Full authentication response: {json.dumps(auth_data, indent=2)}") # Potentially too verbose for regular logs
                    
                    access_token = None
                    token_data = auth_data.get('token')
                    
                    if isinstance(token_data, dict) and 'accessToken' in token_data:
                        access_token = token_data.get('accessToken')
                        expires_in = token_data.get('expiresIn')
                        if expires_in and isinstance(expires_in, (int, float)):
                            buffer = 3600  # 1 hour buffer
                            self.token_expiry = time.time() + (expires_in - buffer)
                        else:
                            self.token_expiry = time.time() + (23 * 60 * 60) # Default 23 hours
                    elif isinstance(token_data, str): # Direct token string
                        access_token = token_data
                        self.token_expiry = time.time() + (23 * 60 * 60)
                    else: # Try alternative common keys
                        access_token = auth_data.get('accessToken', auth_data.get('access_token'))
                        self.token_expiry = time.time() + (23 * 60 * 60)
                        
                    if not access_token:
                        logger.error(f"Could not find token in response: {auth_data}")
                        raise ValueError("No valid token found in authentication response")
                    
                    self.token = access_token
                    logger.info(f"Successfully retrieved new token, valid until: {datetime.datetime.fromtimestamp(self.token_expiry).strftime('%Y-%m-%d %H:%M:%S')}")
                    return # Success, exit refresh method

                # If we are here, it means we need to retry (either 429 or other retryable error)
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"RequestException during auth token retrieval (attempt {current_retry + 1}): {e}")
                if hasattr(e, 'response') and e.response is not None:
                    logger.warning(f"Auth Exception Response status: {e.response.status_code}")
                    logger.warning(f"Auth Exception Response content: {e.response.content.decode('utf-8') if e.response.content else 'No content'}")
                # For RequestException, we'll retry
            
            # Retry logic
            if current_retry < self.MAX_RETRIES:
                logger.info(f"Waiting {backoff_seconds}s before next auth attempt...")
                time.sleep(backoff_seconds)
                current_retry += 1
                backoff_seconds = min(self.MAX_BACKOFF_SECONDS, backoff_seconds * 2) # Exponential backoff
            else:
                logger.error("Max retries reached for authentication. Failing.")
                # If it's an HTTPError from response.raise_for_status(), it will be re-raised.
                # If it's another RequestException, we need to raise it.
                if 'response' in locals() and response and response.status_code != 200 and response.status_code != 429:
                    response.raise_for_status() # Raise the last unsuccessful response's error
                elif 'e' in locals() and isinstance(e, requests.exceptions.RequestException):
                    raise e # Raise the last RequestException
                else: # Fallback if no specific exception was caught and loop finished
                    raise requests.exceptions.RequestException("Max retries reached for authentication after undefined error.")
    
    def _ensure_valid_token(self):
        """Ensure we have a valid authentication token, refreshing if necessary."""
        # If no token or token is expired/expiring soon (within 5 minutes)
        if self.token is None or self.token_expiry is None or time.time() + 300 > self.token_expiry:
            self._refresh_token()
    
    def _make_request(self, endpoint: str, method: str = "GET", params: Optional[Dict] = None, data: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Make a request to the Toast API with retry logic.
        
        Args:
            endpoint: API endpoint to call
            method: HTTP method to use
            params: Query parameters for the request
            data: JSON body for POST requests
            
        Returns:
            Dict containing the API response
            
        Raises:
            requests.exceptions.RequestException: If the API request fails after retries
        """
        # Ensure we have a valid token
        self._ensure_valid_token()
        
        url = f"{self.base_url}{endpoint}"
        
        # Create headers - using restaurant guid
        headers = {
            "Toast-Restaurant-External-ID": self.restaurant_guid,
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        # Debug the headers and parameters
        logger.info(f"Request URL: {url}")
        logger.info(f"Request method: {method}")
        logger.info(f"Request headers: Authorization: Bearer {self.token[:10]}..., Toast-Restaurant-External-ID: {self.restaurant_guid}")
        logger.info(f"Request parameters: {json.dumps(params, indent=2) if params else 'None'}")
        logger.info(f"Request data: {json.dumps(data, indent=2) if data else 'None'}")
        
        current_retry = 0
        backoff_seconds = self.INITIAL_BACKOFF_SECONDS

        while current_retry <= self.MAX_RETRIES:
            try:
                # Ensure token is valid before each attempt (especially important for long backoffs)
                self._ensure_valid_token() 

                # Update headers with potentially refreshed token
                headers["Authorization"] = f"Bearer {self.token}"
                
                logger.info(f"API Call Attempt {current_retry + 1}/{self.MAX_RETRIES + 1} to {url}")

                response = requests.request(
                    method=method,
                    url=url,
                    headers=headers,
                    params=params,
                    json=data,
                    timeout=20 # Increased timeout for data requests
                )
                
                logger.info(f"Response status: {response.status_code}")

                if response.status_code == 401:
                    logger.warning("Received 401 Unauthorized. Token might have expired just before use or is invalid. Refreshing and retrying this attempt.")
                    # Token will be refreshed by _ensure_valid_token() at the start of the next loop or if this was the first attempt by _refresh_token()
                    # We force a refresh here and then continue the loop, which will retry the request.
                    # This attempt won't count as a "failed" retry if the next one succeeds.
                    # However, to avoid tight loops on repeated 401s, we should ensure _refresh_token handles its own retries robustly.
                    # If _refresh_token fails, it will raise, exiting this loop.
                    self._refresh_token() # Force refresh
                    # We don't increment current_retry here if we want the 401 to not count against main retries,
                    # but it's safer to count it to prevent potential infinite loops if _refresh_token() has issues.
                    # For now, let it re-evaluate at the start of the next loop after _ensure_valid_token.
                    # Let's actually continue to the next iteration of the while loop to re-evaluate.
                    # If it was the last retry, it will exit. Otherwise, it retries with fresh token.
                    if current_retry < self.MAX_RETRIES:
                        logger.info(f"Waiting {backoff_seconds}s after 401 before retrying request...")
                        time.sleep(backoff_seconds)
                        current_retry +=1 # Consume a retry attempt for the 401
                        backoff_seconds = min(self.MAX_BACKOFF_SECONDS, backoff_seconds * 2)
                        continue # Jump to next iteration of the while loop
                    else:
                        logger.error("Received 401 on last retry attempt. Failing.")
                        response.raise_for_status() # Fail if 401 on last attempt

                elif response.status_code == 429:
                    logger.warning(f"Received 429 (Too Many Requests). Retrying in {backoff_seconds}s...")
                    # Fall through to the retry sleep logic below
                
                elif response.status_code >= 500: # Server-side errors
                    logger.warning(f"Received server error {response.status_code}. Retrying in {backoff_seconds}s...")
                    # Fall through to the retry sleep logic below

                else: # Includes successful 2xx responses and other client errors (4xx) not handled above
                    response.raise_for_status() # Raise an exception for other 4xx errors immediately
                                                # or if it's a 2xx, this does nothing and proceeds.
                    try:
                        return response.json()
                    except ValueError: # json.JSONDecodeError is a subclass of ValueError
                        logger.error("Response is not JSON. Returning raw text.")
                        return {"rawText": response.text}
                
                # If we are here, it means a 429 or 5xx occurred, and we need to retry.
            
            except requests.exceptions.HTTPError as e:
                # This catches errors raised by response.raise_for_status() for non-2xx codes
                # that are not 401, 429, or 5xx (which are handled above for retries).
                # For example, a 403 Forbidden or 404 Not Found would land here.
                logger.error(f"HTTPError during API request: {e}. Status: {e.response.status_code if e.response else 'N/A'}. No retry for this error.")
                raise # Re-raise immediately, no retry for these.

            except requests.exceptions.RequestException as e:
                # This catches other network-related errors (DNS failure, connection timeout, etc.)
                logger.warning(f"RequestException during API request (attempt {current_retry + 1}): {e}")
                if hasattr(e, 'response') and e.response is not None:
                    logger.warning(f"RequestException Response status: {e.response.status_code if e.response else 'N/A'}")
                # Fall through to the retry sleep logic below

            # Retry logic for 429, 5xx, or general RequestExceptions
            if current_retry < self.MAX_RETRIES:
                logger.info(f"Waiting {backoff_seconds}s before next API call attempt...")
                time.sleep(backoff_seconds)
                current_retry += 1
                backoff_seconds = min(self.MAX_BACKOFF_SECONDS, backoff_seconds * 2) # Exponential backoff
            else: # Max retries reached
                logger.error(f"Max retries reached for API call to {endpoint}. Failing.")
                # If the last error was from response.raise_for_status() for a 429/5xx or a RequestException, re-raise it.
                if 'response' in locals() and response and (response.status_code == 429 or response.status_code >=500):
                    response.raise_for_status() # Raise the last 429/5xx error
                elif 'e' in locals() and isinstance(e, requests.exceptions.RequestException):
                    raise e # Raise the last RequestException
                else: # Fallback if no specific exception was caught and loop finished
                    raise requests.exceptions.RequestException(f"Max retries reached for {endpoint} after undefined error.")
    
    def get_orders(self, start_date: str, end_date: str) -> Dict[str, Any]:
        """
        Fetch all orders from Toast API within a date range.
        
        Args:
            start_date: Start date in ISO format with timezone (e.g. "2025-01-01T05:00:00.000Z")
            end_date: End date in ISO format with timezone (e.g. "2025-01-31T23:59:59.999Z")
            
        Returns:
            Dict containing order data with structure:
            {
                'orders': List[Dict],
                'totalCount': int
            }
            
            If no orders are found, returns an empty list wrapped in a dict:
            {
                'orders': [],
                'totalCount': 0
            }
        """
        # Check if we're dealing with a single day or a date range
        start_date_only = start_date.split("T")[0]
        end_date_only = end_date.split("T")[0]
        is_single_day = start_date_only == end_date_only
        
        # If it's a single day, use businessDate which is more efficient
        # Otherwise, use date range (startDate and endDate parameters)
        if is_single_day:
            # Format businessDate in yyyymmdd format as required by API
            date_obj = datetime.datetime.strptime(start_date_only, "%Y-%m-%d")
            business_date = date_obj.strftime("%Y%m%d")
            logger.info(f"Single day request - Using businessDate: {business_date}")
            param_type = "businessDate"
        else:
            logger.info(f"Date range request - Using startDate: {start_date} and endDate: {end_date}")
            param_type = "dateRange"
        
        # Initialize variables for pagination
        all_orders = []
        page = 1
        page_size = 100  # Maximum allowed by the API
        more_records = True
        
        logger.info("Starting pagination to fetch all orders...")
        
        # Rate limiting parameters
        requests_count = 0
        rate_limit_threshold = 10  # Max requests per minute (adjust based on API limits)
        rate_limit_window = 60     # Time window in seconds
        start_time = time.time()
        
        while more_records:
            # Check rate limiting
            requests_count += 1
            elapsed_time = time.time() - start_time
            
            if requests_count >= rate_limit_threshold and elapsed_time < rate_limit_window:
                # We're approaching rate limit, need to sleep
                sleep_time = rate_limit_window - elapsed_time + 1  # Add 1 second buffer
                logger.info(f"Rate limit approached. Sleeping for {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
                # Reset counter
                requests_count = 0
                start_time = time.time()
            
            # Set parameters based on current pagination state and parameter type
            if param_type == "businessDate":
                date_obj = datetime.datetime.strptime(start_date_only, "%Y-%m-%d")
                business_date = date_obj.strftime("%Y%m%d")
                params = {
                    "businessDate": business_date,
                    "page": str(page),
                    "pageSize": str(page_size)
                }
            else:
                params = {
                    "startDate": start_date,
                    "endDate": end_date,
                    "page": str(page),
                    "pageSize": str(page_size)
                }
            
            logger.info(f"Fetching page {page} with {page_size} items per page using {param_type} parameter...")
            
            try:
                # Make the API request for this page
                result = self._make_request("/orders/v2/ordersBulk", params=params)
                
                # Handle the result based on its type
                if isinstance(result, list):
                    page_orders = result
                    logger.info(f"Received list with {len(page_orders)} orders for page {page}")
                elif isinstance(result, dict) and 'orders' in result:
                    page_orders = result.get('orders', [])
                    logger.info(f"Received dictionary with {len(page_orders)} orders for page {page}")
                else:
                    logger.error(f"Unexpected response format for page {page}. Keys: {', '.join(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
                    page_orders = []
                
                # Add this page's orders to our accumulated list
                all_orders.extend(page_orders)
                
                # Determine if there are more pages to fetch
                if len(page_orders) < page_size:
                    # We received fewer items than the page size, so we've reached the end
                    more_records = False
                    logger.info(f"Reached end of data with {len(page_orders)} items on page {page}")
                else:
                    # There might be more pages, increment page number
                    page += 1
                    logger.info(f"Moving to page {page}...")
                    
                    # Add a small delay between requests to be gentle on the API
                    time.sleep(0.5)
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Error fetching page {page} with {param_type}: {e}")
                
                # If we're using businessDate and encounter an error, try with date range instead
                if param_type == "businessDate" and page == 1:
                    logger.info("Switching to date range parameters instead of businessDate...")
                    param_type = "dateRange"
                    # Reset page counter
                    page = 1
                    all_orders = []
                    continue
                
                # If we've already tried both parameter types or we're beyond page 1, just return what we have
                break
        
        # Return all accumulated orders
        total_count = len(all_orders)
        logger.info(f"Successfully fetched a total of {total_count} orders across {page} pages")
        
        return {
            'orders': all_orders,
            'totalCount': total_count
        }
    
    def get_menus(self) -> Dict[str, Any]:
        """
        Fetch menu data from the Toast API.
        
        Returns:
            Dict containing menu data
            
        Raises:
            requests.exceptions.RequestException: If the API request fails
        """
        endpoint = "/menus/v2/menus"
        return self._make_request(endpoint)
    
    def get_employee(self, employee_guid: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetch employee information from the Toast API.
        
        Args:
            employee_guid: Optional GUID of the employee to retrieve. If None, fetches all employees.
            
        Returns:
            Dict containing employee data
            
        Raises:
            requests.exceptions.RequestException: If the API request fails
        """
        endpoint = "/labor/v1/employees"
        params = {}
        if employee_guid:
            params["employeeIds"] = employee_guid
        return self._make_request(endpoint, params=params if params else None)
    
    def get_time_entries(self, start_date: str, end_date: str, include_archived: bool = True, 
                        include_missed_breaks: bool = True, time_entry_ids: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetch time entries from the Toast API using date range format.
        
        Args:
            start_date: Start date in ISO format (e.g. "2025-01-01T00:00:00.000Z")
            end_date: End date in ISO format (e.g. "2025-01-31T23:59:59.999Z")
            include_archived: Whether to include archived time entries (default: True)
            include_missed_breaks: Whether to include missed breaks (default: True)
            time_entry_ids: Comma-separated list of time entry IDs to filter
            
        Returns:
            Dict containing time entries data
            
        Raises:
            requests.exceptions.RequestException: If the API request fails
        """
        endpoint = "/labor/v1/timeEntries"
        params = {
            "startDate": start_date,
            "endDate": end_date
        }
        
        if include_archived:
            params["includeArchived"] = str(include_archived).lower()
        if include_missed_breaks:
            params["includeMissedBreaks"] = str(include_missed_breaks).lower()
        if time_entry_ids:
            params["timeEntryIds"] = time_entry_ids
            
        return self._make_request(endpoint, params=params)
    
    def get_jobs(self, job_ids: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetch jobs from the Toast API.
        
        Args:
            job_ids: Optional comma-separated list of job IDs to filter
            
        Returns:
            Dict containing jobs data
            
        Raises:
            requests.exceptions.RequestException: If the API request fails
        """
        endpoint = "/labor/v1/jobs"
        params = {}
        if job_ids:
            params["jobIds"] = job_ids
        return self._make_request(endpoint, params=params if params else None)