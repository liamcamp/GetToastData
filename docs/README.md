# Toast API Integration

This project provides a Python-based integration with the Toast POS API, allowing you to:
- Retrieve order information and process it
- Send processed data to a webhook
- Test API configuration and authentication

## Prerequisites

- Python 3.7 or higher
- Toast API credentials (client ID and client secret)
- Toast restaurant GUID
- Appropriate permissions to access order data in Toast

## Installation

1. Clone this repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.template` to `.env` and fill in your credentials:
   ```bash
   cp .env.template .env
   ```

## Configuration

Edit the `.env` file with your Toast API credentials:
```
TOAST_CLIENT_ID=your_client_id
TOAST_CLIENT_SECRET=your_client_secret
TOAST_RESTAURANT_GUID=your_restaurant_guid
WEBHOOK_URL=your_webhook_url  # Optional
```

## Usage

### Getting Order Information

The `get_orders.py` script allows you to retrieve order information from the Toast API. This includes order details, items, and payment information.

```bash
python get_orders.py [options]
```

Options:
- `--date YYYY-MM-DD`: Specify a date to retrieve orders from (defaults to today)
- `--dates YYYY-MM-DD YYYY-MM-DD`: Specify a date range to retrieve orders from
- `--process`: Process the order data to extract relevant information
- `--webhook`: Send the data to the configured webhook URL
- `--output-file FILENAME`: Save the order data to a file
- `--location-index INDEX`: Specify a restaurant by its location index

Examples:
```bash
# Get today's orders
python get_orders.py

# Get orders for a specific date
python get_orders.py --date 2024-03-25

# Save orders to a file
python get_orders.py --output-file orders.json

# Process orders and send to webhook
python get_orders.py --process --webhook
```

### Testing Configuration

To test your API configuration and authentication:

```bash
python main.py --test-config
```

This will verify your credentials and webhook configuration.

## Error Handling

The scripts include error handling for common issues:
- Invalid credentials
- API rate limiting
- Network connectivity issues
- Invalid data formats

## Contributing

Feel free to submit issues and enhancement requests!

## Web Server API

The project includes a Flask web server (`server.py`) that provides an HTTP endpoint for running the order processing script remotely.

### Running the Server

```bash
python server.py
```

The server will start on port 5000.

### API Endpoint: `/run`

Send a POST request to `http://your-server:5000/run` with the following JSON payload:

```json
{
  "startDate": "2025-01-07",
  "endDate": "2025-01-07",
  "process": true,
  "webhook": true,
  "locationIndex": 4
}
```

#### Webhook Parameter Options

The `webhook` parameter now supports three different options:

1. **Boolean `true`**: Use the default webhook URL configured in the system
   ```json
   {
     "webhook": true
   }
   ```

2. **String URL**: Send data to a custom webhook URL
   ```json
   {
     "webhook": "https://your-custom-webhook.com/endpoint"
   }
   ```

3. **Boolean `false`**: Process data without sending to any webhook
   ```json
   {
     "webhook": false
   }
   ```

#### Full Example with Custom Webhook

```json
{
  "startDate": "2025-01-07",
  "endDate": "2025-01-07",
  "process": true,
  "webhook": "https://my-custom-webhook.com/orders",
  "locationIndex": 4
}
```

This will process the orders for the specified date range and location, then send the results to your custom webhook URL instead of the default one. 