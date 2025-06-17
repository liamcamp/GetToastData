import json
import traceback

# Define the set of KNOWN Sales Category GUIDs for Location 4 (Original Joe's - North Beach)
# Items with these GUIDs should NOT be in 'Other'
KNOWN_LOCATION_4_GUIDS = {
    "758a34df-b27f-419a-81b8-2c56a663f15b", # Food
    "64a6a7fb-f3ce-4f2f-936d-39118bda785f", # NA Beverage
    "dc3bad48-66ff-4183-9cd3-7a3552ab5973", # Liquor
    "ef6790cb-64f3-4887-84b2-fd348dac46a9", # Beer Bottle
    "fcd1cbdc-361f-4f66-93f2-53467adfd134", # Beer Keg
    "d0ea6c37-bf62-415a-a40d-6a4a824bb661", # Wine Bottle
    "3e611002-7c96-4b20-a228-a05efc70c2c3", # Wine Keg
}

def analyze_source_vs_null_sales_category(filename="oj_nb_3-17_3-23.json"):
    """
    Analyzes orders in a JSON file to correlate order source ('API', 'In Store', etc.)
    with the occurrence of null salesCategory in MenuItemSelections.
    """
    stats = {
        # Using more descriptive keys based on common Toast source values
        "POS": {"orders": 0, "selections": 0, "null_sc_selections": 0},
        "ONLINE_ORDERING": {"orders": 0, "selections": 0, "null_sc_selections": 0},
        "API": {"orders": 0, "selections": 0, "null_sc_selections": 0},
        "OTHER": {"orders": 0, "selections": 0, "null_sc_selections": 0, "sources_seen": set()},
        "UNKNOWN": {"orders": 0, "selections": 0, "null_sc_selections": 0},
        "total_null_sc_selections": 0,
    }
    valid_sources = {"POS", "ONLINE_ORDERING", "API"} # Known primary sources

    try:
        with open(filename, 'r') as f:
            raw_data = json.load(f)

        # Expecting structure like {'orders': [...]} based on get_orders.py context
        orders_list = raw_data.get('orders')
        if not isinstance(orders_list, list):
            print(f"Error: Could not find a list under the 'orders' key in {filename}.")
            # Attempt fallback: maybe the file IS the list of orders
            if isinstance(raw_data, list):
                 print("Warning: Input JSON is a list, not a dict with 'orders'. Processing list directly.")
                 orders_list = raw_data
            else:
                 return None


        print(f"Analyzing {len(orders_list)} orders...")

        for order in orders_list:
            # Normalize source for consistent checking
            source = order.get("source", "UNKNOWN")
            order_key = "UNKNOWN" # Default key

            if source in valid_sources:
                 order_key = source
            elif source != "UNKNOWN":
                 order_key = "OTHER"
                 stats["OTHER"]["sources_seen"].add(source) # Track specific other sources

            stats[order_key]["orders"] += 1

            # Iterate through selections within this order
            order_selections_count = 0
            order_null_sc_count = 0
            for check in order.get('checks', []):
                for selection in check.get('selections', []):
                    # Exclude voided/gift cards for consistency
                    if selection.get('voided', False): continue
                    display_name = selection.get('displayName', '').strip()
                    if display_name in ['Gift Card', 'eGift Card']: continue

                    # Only interested in MenuItemSelection entities
                    if selection.get("entityType") == "MenuItemSelection":
                        order_selections_count += 1
                        # Check specifically for salesCategory being null
                        if selection.get("salesCategory") is None:
                            order_null_sc_count += 1

            # Add counts to the correct source bucket
            stats[order_key]["selections"] += order_selections_count
            stats[order_key]["null_sc_selections"] += order_null_sc_count
            stats["total_null_sc_selections"] += order_null_sc_count # Overall total

    except FileNotFoundError:
        print(f"Error: File not found at {filename}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Could not decode JSON from {filename}. Error: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        print(traceback.format_exc())
        return None

    return stats

if __name__ == "__main__":
    analysis_results = analyze_source_vs_null_sales_category()

    if analysis_results:
        print("\n--- Analysis Results: Order Source vs. Null SalesCategory ---")
        total_orders = sum(analysis_results[k]["orders"] for k in analysis_results if isinstance(analysis_results[k], dict))
        total_selections = sum(analysis_results[k]["selections"] for k in analysis_results if isinstance(analysis_results[k], dict))

        print(f"Total Orders Analyzed: {total_orders}")
        print(f"Total MenuItemSelections Analyzed (non-voided/gc): {total_selections}")
        print(f"Total Selections w/ Null SalesCategory: {analysis_results['total_null_sc_selections']}")
        print("-" * 60)

        # Define the order of keys to print
        source_keys_to_print = ["POS", "ONLINE_ORDERING", "API", "OTHER", "UNKNOWN"]

        for source_key in source_keys_to_print:
            # Check if the key exists and has data before printing
            if source_key in analysis_results and isinstance(analysis_results[source_key], dict):
                 data = analysis_results[source_key]
                 if data["orders"] > 0: # Only print if there were orders from this source
                     print(f"Source: {source_key}")
                     if source_key == "OTHER" and data["sources_seen"]:
                         print(f"  (Specific sources seen: {', '.join(sorted(list(data['sources_seen'])))})")
                     print(f"  Orders: {data['orders']}")
                     print(f"  MenuItemSelections: {data['selections']}")
                     print(f"  Selections w/ Null SalesCategory: {data['null_sc_selections']}")
                     # Calculate percentage safely
                     perc_null = (data['null_sc_selections'] / data['selections'] * 100) if data['selections'] > 0 else 0
                     print(f"  % Selections w/ Null SalesCategory: {perc_null:.2f}%")
                     print("-" * 20)

    else:
        print("Analysis could not be completed due to errors.") 