# Transcripts - apex_hyperstore

## T10_error_code - FAIL
**user:** Checkout keeps failing with error APX-4021. My UPI money is debited but no order is created. What do I do?
- `apex_concierge` -> tool `transfer_to_agent` {"agent_name": "support_agent"}
- tool result `transfer_to_agent`: {"result": null}
- `support_agent` -> tool `search_knowledge_base` {"query": "APX-4021"}
- tool result `search_knowledge_base`: {"status": "ok", "query": "APX-4021", "count": 3, "articles": [{"kb_id": "APX-KB-0101", "topic": "Checkout", "error_code": "APX-4021", "surface": "Apex app / website", "symptom": "\"Payment failed (APX-4021)\" at checkout although UPI request was debited.", "cause": "UPI mandate succeeded at the ban
- `support_agent` -> tool `check_system_status` {"service": "Checkout & Payments"}
- tool result `check_system_status`: {"status": "ok", "services": [{"service": "Checkout & Payments", "status": "degraded", "incident": "Elevated UPI callback latency (APX-4021 retries). Started 2026-10-17T06:10:00.", "updated_at": "2026-10-17T09:30:00"}], "degraded_services": ["Checkout & Payments"], "message": "Currently degraded: Ch
- `support_agent`: I am sorry you are experiencing this issue. We are currently seeing elevated UPI callback latency, which is causing the APX-4021 error you mentioned.

Please follow these steps to resolve this:
1. Check your bank app to see if there is a pending mandate. If so, please reverse it.
2. Please do not retry the checkout immediately while the service is degraded.

Since your money was debited, I need to transfer you to our orders team to ensure your payment is tracked correctly and to assist with any refund if necessary.


- `support_agent` -> tool `transfer_to_agent` {"agent_name": "orders_agent"}
- tool result `transfer_to_agent`: {"result": null}
- `orders_agent`: I understand how frustrating it is to have your money debited without an order being created. I am here to help you get this resolved.

Since our payment systems are currently experiencing some latency, please check your bank app to see if there is a pending mandate. If you find one, please reverse it. 

To ensure we track this payment correctly and assist you further, could you please provide me with your registered email address? I will then be able to look into this for you. Please remember, never share your UPI PIN, OTP, or CVV with anyone.
state: {}

## T11_system_status - PASS
**user:** Is payment failing for everyone right now or is it just me?
- `apex_concierge` -> tool `transfer_to_agent` {"agent_name": "support_agent"}
- tool result `transfer_to_agent`: {"result": null}
- `support_agent` -> tool `check_system_status` {"service": "Checkout & Payments"}
- tool result `check_system_status`: {"status": "ok", "services": [{"service": "Checkout & Payments", "status": "degraded", "incident": "Elevated UPI callback latency (APX-4021 retries). Started 2026-10-17T06:10:00.", "updated_at": "2026-10-17T09:30:00"}], "degraded_services": ["Checkout & Payments"], "message": "Currently degraded: Ch
- `support_agent`: We are currently experiencing some issues with Checkout & Payments, which may be causing the failures you are seeing. This is due to elevated UPI callback latency, tracked under incident APX-4021.

Our team is working on this, and we hope to have it resolved soon. Please let me know if you would like me to raise a service request so we can notify you once the service is fully restored.
state: {}

## T12_coupon_problem - PASS
**user:** My coupon keeps getting rejected at the payment page. Why?
- `apex_concierge` -> tool `transfer_to_agent` {"agent_name": "support_agent"}
- tool result `transfer_to_agent`: {"result": null}
- `support_agent` -> tool `search_knowledge_base` {"query": "coupon rejected at payment page"}
- tool result `search_knowledge_base`: {"status": "ok", "query": "coupon rejected at payment page", "count": 3, "articles": [{"kb_id": "APX-KB-0105", "topic": "Payments", "error_code": "APX-4305", "surface": "Website", "symptom": "Coupon code is rejected with \"APX-4305: coupon not applicable\".", "cause": "The cart contains a category t
- `support_agent` -> tool `get_troubleshooting_guide` {"kb_id": "APX-KB-0105"}
- tool result `get_troubleshooting_guide`: {"status": "ok", "article": {"kb_id": "APX-KB-0105", "topic": "Payments", "error_code": "APX-4305", "surface": "Website", "symptom": "Coupon code is rejected with \"APX-4305: coupon not applicable\".", "cause": "The cart contains a category that is excluded from the coupon, or the coupon expired at 
- `support_agent`: I am sorry to hear you are having trouble with your coupon. This usually happens if the items in your cart are excluded from the offer or if the coupon has expired.

Could you please check if you see an error code like "APX-4305" on your screen? Also, please note that grocery subscriptions and items purchased via EMI are often excluded from promotional coupons.

If you are still having trouble, please let me know what the exact error message says, and I would be happy to look into this further for you.
state: {}
