"""Configuration management for the Toast API integration."""
import os
import logging
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("config.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("toast-config")

# Load environment variables from .env file
load_dotenv()

# Location to GUID mapping
LOCATION_GUID_MAP = {
    1: "8a3b1856-f4ed-4f13-8f64-6349fbffe1f1",
    2: "424bca99-0858-4c55-9fe6-ba3936f2fe1b",
    3: "09017aed-dc03-494c-a1b1-cbb0b71a0141",
    4: "2058e275-2eff-4cf0-8eeb-12001129d782",
    5: "2437b9ff-00d5-4cec-b629-704f72e5f5ae"
}

# Toast API Configuration
TOAST_API_BASE_URL = os.getenv('TOAST_API_BASE_URL', 'https://ws-api.toasttab.com')
TOAST_AUTH_URL = os.getenv('TOAST_AUTH_URL', 'https://ws-api.toasttab.com/authentication/v1/authentication/login')
TOAST_API_KEY = os.getenv('TOAST_API_KEY')

# Get location index from environment
location_index = os.getenv('TOAST_LOCATION_INDEX')
logger.info(f"Config module loaded. Raw TOAST_LOCATION_INDEX from environment: '{location_index}'")

if location_index:
    try:
        location_index = int(location_index)
        logger.info(f"Parsed location_index as integer: {location_index}")
        
        if location_index not in LOCATION_GUID_MAP:
            logger.error(f"Invalid location index: {location_index}. Must be between 1 and 5.")
            raise ValueError(f"Invalid location index: {location_index}. Must be between 1 and 5.")
        
        TOAST_RESTAURANT_GUID = LOCATION_GUID_MAP[location_index]
        logger.info(f"Using TOAST_RESTAURANT_GUID: {TOAST_RESTAURANT_GUID} from LOCATION_GUID_MAP for location index {location_index}")
    except ValueError as e:
        logger.error(f"Invalid TOAST_LOCATION_INDEX: {e}")
        raise ValueError(f"Invalid TOAST_LOCATION_INDEX: {e}")
else:
    # Fallback to direct GUID if provided
    TOAST_RESTAURANT_GUID = os.getenv('TOAST_RESTAURANT_GUID')
    logger.info(f"No location index found, using direct TOAST_RESTAURANT_GUID from environment: {TOAST_RESTAURANT_GUID}")

# Toast API Authentication
TOAST_CLIENT_ID = os.getenv('TOAST_CLIENT_ID')
TOAST_CLIENT_SECRET = os.getenv('TOAST_CLIENT_SECRET')

# Validate required environment variables
required_vars = [
    'TOAST_CLIENT_ID',
    'TOAST_CLIENT_SECRET'
]

# Add GUID validation - either TOAST_LOCATION_INDEX or TOAST_RESTAURANT_GUID must be set
if not TOAST_RESTAURANT_GUID and not location_index:
    required_vars.append('TOAST_LOCATION_INDEX or TOAST_RESTAURANT_GUID')
    logger.error("Missing both TOAST_LOCATION_INDEX and TOAST_RESTAURANT_GUID")

missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    error_msg = f"Missing required environment variables: {', '.join(missing_vars)}"
    logger.error(error_msg)
    raise ValueError(error_msg)
    
logger.info(f"Config module initialized successfully with TOAST_RESTAURANT_GUID: {TOAST_RESTAURANT_GUID}") 