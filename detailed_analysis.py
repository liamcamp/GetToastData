#!/usr/bin/env python3
import json
from datetime import datetime, timezone, timedelta

def detailed_date_analysis(filename):
    print(f"DETAILED DATE ASSIGNMENT ANALYSIS")
    print("=" * 60)
    
    with open(filename, 'r') as f:
        data = json.load(f)
    
    orders = data.get('orders', [])
    
    problematic_cases = []
    
    for order in orders:
        checks = order.get('checks', [])
        if not checks:
            continue
            
        for check in checks:
            for payment in check.get('payments', []):
                tip_amount = payment.get('tipAmount', 0)
                if tip_amount > 0:
                    business_date = payment.get('paidBusinessDate')
                    if isinstance(business_date, int):
                        business_date_str = f"{str(business_date)[:4]}-{str(business_date)[4:6]}-{str(business_date)[6:]}"
                    else:
                        business_date_str = str(business_date)
                    
                    # Only look at problematic cases (not June 24)
                    if business_date_str not in ['2025-06-24', '2024-06-24']:
                        case = {
                            'orderId': order.get('guid'),
                            'displayNumber': order.get('displayNumber'),
                            'orderOpenedDate': order.get('openedDate'),
                            'orderPaidDate': order.get('paidDate'),
                            'checkId': check.get('guid'),
                            'checkOpenedDate': check.get('openedDate'),
                            'checkPaidDate': check.get('paidDate'),
                            'paymentId': payment.get('guid'),
                            'paymentPaidDate': payment.get('paidDate'),
                            'businessDate': business_date_str,
                            'businessDateRaw': business_date,
                            'tipAmount': tip_amount,
                            'paymentAmount': payment.get('amount', 0),
                            'refundInfo': payment.get('refund')
                        }
                        problematic_cases.append(case)
    
    print(f"Found {len(problematic_cases)} problematic tip assignments")
    print()
    
    # Analyze each problematic case
    for i, case in enumerate(problematic_cases):
        print(f"PROBLEMATIC CASE #{i+1}:")
        print(f"  Order ID: {case['orderId']}")
        print(f"  Display Number: {case['displayNumber']}")
        print(f"  Tip Amount: ${case['tipAmount']:.2f}")
        print(f"  Payment Amount: ${case['paymentAmount']:.2f}")
        print(f"  Business Date: {case['businessDate']} (raw: {case['businessDateRaw']})")
        print()
        
        # Date analysis
        print("  DATE ANALYSIS:")
        print(f"    Order Opened:   {case['orderOpenedDate']}")
        print(f"    Order Paid:     {case['orderPaidDate']}")
        print(f"    Check Opened:   {case['checkOpenedDate']}")
        print(f"    Check Paid:     {case['checkPaidDate']}")
        print(f"    Payment Paid:   {case['paymentPaidDate']}")
        print()
        
        # Time zone analysis
        try:
            if case['paymentPaidDate']:
                payment_dt = datetime.fromisoformat(case['paymentPaidDate'].replace('Z', '+00:00'))
                
                # Convert to different time zones to understand business date logic
                utc_time = payment_dt.replace(tzinfo=timezone.utc)
                # Approximate EST/PST without pytz
                est_offset = timedelta(hours=-5)  # EST is UTC-5 (not accounting for DST)
                pst_offset = timedelta(hours=-8)  # PST is UTC-8 (not accounting for DST)
                est_time = utc_time + est_offset
                pst_time = utc_time + pst_offset
                
                print("  TIMEZONE ANALYSIS:")
                print(f"    UTC:     {utc_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                print(f"    EST:     {est_time.strftime('%Y-%m-%d %H:%M:%S')} (approx)")
                print(f"    PST:     {pst_time.strftime('%Y-%m-%d %H:%M:%S')} (approx)")
                print()
                
                # Business date logic analysis
                print("  BUSINESS DATE LOGIC ANALYSIS:")
                print(f"    If business day starts at midnight UTC: {utc_time.strftime('%Y-%m-%d')}")
                print(f"    If business day starts at midnight EST: {est_time.strftime('%Y-%m-%d')}")
                print(f"    If business day starts at midnight PST: {pst_time.strftime('%Y-%m-%d')}")
                
                # Check if business date cutoff might be different
                if utc_time.hour < 6:  # Before 6 AM UTC
                    prev_day_utc = (utc_time.replace(hour=0, minute=0, second=0) - 
                                  timedelta(days=1)).strftime('%Y-%m-%d')
                    print(f"    If business day ends at 6 AM UTC: {prev_day_utc}")
                
                print()
                
        except Exception as e:
            print(f"    Error parsing payment date: {e}")
            print()
        
        # Refund analysis
        if case['refundInfo']:
            print("  REFUND INFORMATION:")
            refund = case['refundInfo']
            print(f"    Refund Amount: ${refund.get('refundAmount', 0):.2f}")
            print(f"    Tip Refund Amount: ${refund.get('tipRefundAmount', 0):.2f}")
            print(f"    Refund Date: {refund.get('refundDate')}")
            print(f"    Refund Business Date: {refund.get('refundBusinessDate')}")
            print()
        
        print("-" * 80)
        print()

if __name__ == "__main__":
    detailed_date_analysis("oj_wl_orders_june_24.json")