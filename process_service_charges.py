import json
from typing import Dict, List, Any
from decimal import Decimal, ROUND_DOWN

def calculate_item_percentages(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Calculate the percentage of total for each food item.
    Returns items with added percentage field.
    """
    # Calculate total subtotal of all items
    total_subtotal = sum(
        Decimal(str(item.get('subtotal', 0)))
        for item in items
        if item.get('entityType') == 'LineItem'
    )
    
    if total_subtotal == 0:
        return items
    
    # Calculate percentage for each item
    for item in items:
        if item.get('entityType') == 'LineItem':
            item_subtotal = Decimal(str(item.get('subtotal', 0)))
            percentage = (item_subtotal / total_subtotal) * 100
            item['percentage_of_total'] = float(percentage)
    
    return items

def attribute_service_charges(order: Dict[str, Any]) -> Dict[str, Any]:
    """
    Attribute service charges to food items based on percentage of total.
    Returns modified order with attributed service charges.
    """
    # Deep copy the order to avoid modifying the original
    processed_order = json.loads(json.dumps(order))
    
    # Get all items and service charges
    items = processed_order.get('items', [])
    service_charges = processed_order.get('appliedServiceCharges', [])
    
    if not service_charges:
        return processed_order
    
    # Calculate percentages for each item
    items_with_percentages = calculate_item_percentages(items)
    
    # Attribute each service charge
    for service_charge in service_charges:
        charge_amount = Decimal(str(service_charge.get('amount', 0)))
        
        # Distribute the charge amount among items
        remaining_amount = charge_amount
        for item in items_with_percentages:
            if item.get('entityType') == 'LineItem':
                # Calculate attributed amount
                attributed_amount = (charge_amount * Decimal(str(item['percentage_of_total']))) / 100
                # Round down to 2 decimal places
                attributed_amount = attributed_amount.quantize(Decimal('0.01'), rounding=ROUND_DOWN)
                
                # Add to item's total
                item['total'] = float(Decimal(str(item.get('total', 0))) + attributed_amount)
                remaining_amount -= attributed_amount
        
        # Handle any remaining amount due to rounding
        if remaining_amount > 0:
            # Add to the last item
            for item in reversed(items_with_percentages):
                if item.get('entityType') == 'LineItem':
                    item['total'] = float(Decimal(str(item['total'])) + remaining_amount)
                    break
    
    # Update the order with processed items
    processed_order['items'] = items_with_percentages
    
    return processed_order

def process_orders_file(input_file: str, output_file: str) -> None:
    """
    Process all orders in a JSON file and save the results.
    """
    with open(input_file, 'r') as f:
        orders = json.load(f)
    
    processed_orders = []
    for order in orders:
        processed_order = attribute_service_charges(order)
        processed_orders.append(processed_order)
    
    with open(output_file, 'w') as f:
        json.dump(processed_orders, f, indent=2)

if __name__ == "__main__":
    input_file = "2024-12-30_2025-01-05.json"
    output_file = "2024-12-30_2025-01-05_with_attributed_charges.json"
    process_orders_file(input_file, output_file) 