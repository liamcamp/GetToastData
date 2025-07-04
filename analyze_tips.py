#!/usr/bin/env python3
import json
from collections import defaultdict
from datetime import datetime

def analyze_tips_dates(filename):
    print(f"Analyzing tip date assignments in {filename}")
    print("=" * 60)
    
    with open(filename, 'r') as f:
        data = json.load(f)
    
    # Extract orders from the data structure
    orders = data.get('orders', [])
    
    tip_analysis = []
    date_distribution = defaultdict(float)
    
    for order in orders:
        checks = order.get('checks', [])
        if not checks:
            continue
            
        order_info = {
            'orderId': order.get('guid'),
            'displayNumber': order.get('displayNumber'),
            'openedDate': order.get('openedDate'),
            'paidDate': order.get('paidDate'),
            'tips': []
        }
        
        has_tips = False
        for check in checks:
            for payment in check.get('payments', []):
                tip_amount = payment.get('tipAmount', 0)
                if tip_amount > 0:
                    has_tips = True
                    # Convert business date from int to string format if needed
                    business_date = payment.get('paidBusinessDate')
                    if isinstance(business_date, int):
                        business_date_str = f"{str(business_date)[:4]}-{str(business_date)[4:6]}-{str(business_date)[6:]}"
                    else:
                        business_date_str = str(business_date)
                    
                    tip_info = {
                        'tipAmount': tip_amount,
                        'paidBusinessDate': business_date_str,
                        'paidDate': payment.get('paidDate'),
                        'checkId': check.get('guid'),
                        'paymentId': payment.get('guid')
                    }
                    order_info['tips'].append(tip_info)
                    
                    # Track date distribution
                    date_distribution[business_date_str] += tip_amount
        
        if has_tips:
            tip_analysis.append(order_info)
    
    # Print summary statistics
    print(f"Total orders with tips: {len(tip_analysis)}")
    print(f"Total tip payments found: {sum(len(order['tips']) for order in tip_analysis)}")
    print("\nTip amount distribution by business date:")
    for date, amount in sorted(date_distribution.items()):
        print(f"  {date}: ${amount:.2f}")
    
    # Find examples of problematic dates
    print("\nDetailed analysis of first 10 orders with tips:")
    print("-" * 80)
    
    for i, order in enumerate(tip_analysis[:10]):
        print(f"\nOrder {i+1}: {order['orderId']}")
        print(f"  Order opened: {order['openedDate']}")
        print(f"  Order paid: {order['paidDate']}")
        
        for j, tip in enumerate(order['tips']):
            print(f"  Tip {j+1}:")
            print(f"    Amount: ${tip['tipAmount']:.2f}")
            print(f"    Business Date: {tip['paidBusinessDate']}")
            print(f"    Payment Date: {tip['paidDate']}")
            
            # Check for date mismatches
            if tip['paidBusinessDate'] not in ['2025-06-24', '2024-06-24']:
                print(f"    *** POTENTIAL ISSUE: Business date is {tip['paidBusinessDate']} instead of June 24 ***")
    
    # Look for patterns in problematic dates
    print("\n" + "=" * 60)
    print("PATTERN ANALYSIS:")
    print("=" * 60)
    
    june22_tips = []
    june23_tips = []
    june24_tips = []
    other_tips = []
    
    for order in tip_analysis:
        for tip in order['tips']:
            business_date = tip['paidBusinessDate']
            tip_with_order = {**tip, 'orderId': order['orderId'], 'orderOpenedDate': order['openedDate'], 'orderPaidDate': order['paidDate']}
            if business_date == '2025-06-22':
                june22_tips.append(tip_with_order)
            elif business_date == '2025-06-23':
                june23_tips.append(tip_with_order)
            elif business_date in ['2025-06-24', '2024-06-24']:
                june24_tips.append(tip_with_order)
            else:
                other_tips.append(tip_with_order)
    
    print(f"Tips assigned to June 22: {len(june22_tips)} (${sum(tip['tipAmount'] for tip in june22_tips):.2f})")
    print(f"Tips assigned to June 23: {len(june23_tips)} (${sum(tip['tipAmount'] for tip in june23_tips):.2f})")
    print(f"Tips assigned to June 24: {len(june24_tips)} (${sum(tip['tipAmount'] for tip in june24_tips):.2f})")
    print(f"Tips assigned to other dates: {len(other_tips)} (${sum(tip['tipAmount'] for tip in other_tips):.2f})")
    
    # Analyze June 22 tips in detail
    if june22_tips:
        print(f"\nDETAIL: Tips incorrectly assigned to June 22 ({len(june22_tips)} tips):")
        for tip in june22_tips[:5]:  # Show first 5 examples
            print(f"  Order {tip['orderId']}: ${tip['tipAmount']:.2f}")
            print(f"    Order opened: {tip['orderOpenedDate']}")
            print(f"    Order paid: {tip['orderPaidDate']}")
            print(f"    Payment date: {tip['paidDate']}")
            print(f"    Business date: {tip['paidBusinessDate']}")
            
            # Try to identify the pattern
            if tip['paidDate']:
                try:
                    payment_dt = datetime.fromisoformat(tip['paidDate'].replace('Z', '+00:00'))
                    print(f"    Payment time: {payment_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                except:
                    print(f"    Payment time: Could not parse {tip['paidDate']}")
            print()
    
    # Analyze June 23 tips in detail
    if june23_tips:
        print(f"\nDETAIL: Tips incorrectly assigned to June 23 ({len(june23_tips)} tips):")
        for tip in june23_tips[:5]:  # Show first 5 examples
            print(f"  Order {tip['orderId']}: ${tip['tipAmount']:.2f}")
            print(f"    Order opened: {tip['orderOpenedDate']}")
            print(f"    Order paid: {tip['orderPaidDate']}")
            print(f"    Payment date: {tip['paidDate']}")
            print(f"    Business date: {tip['paidBusinessDate']}")
            
            # Try to identify the pattern
            if tip['paidDate']:
                try:
                    payment_dt = datetime.fromisoformat(tip['paidDate'].replace('Z', '+00:00'))
                    print(f"    Payment time: {payment_dt.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                except:
                    print(f"    Payment time: Could not parse {tip['paidDate']}")
            print()

if __name__ == "__main__":
    analyze_tips_dates("oj_wl_orders_june_24.json")