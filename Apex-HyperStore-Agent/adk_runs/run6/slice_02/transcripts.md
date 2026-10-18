# Transcripts - apex_hyperstore

## T12_coupon_problem - PASS
**user:** My coupon keeps getting rejected at the payment page. Why?
- `apex_concierge` -> tool `transfer_to_agent` {"agent_name": "support_agent"}
- tool result `transfer_to_agent`: {"result": null}
- `support_agent` -> tool `search_knowledge_base` {"query": "coupon rejected at payment page"}
- tool result `search_knowledge_base`: {"status": "ok", "query": "coupon rejected at payment page", "count": 3, "articles": [{"kb_id": "APX-KB-0105", "topic": "Payments", "error_code": "APX-4305", "surface": "Website", "symptom": "Coupon code is rejected with \"APX-4305: coupon not applicable\".", "cause": "The cart contains a category t
- `support_agent` -> tool `get_troubleshooting_guide` {"kb_id": "APX-KB-0105"}
- tool result `get_troubleshooting_guide`: {"status": "ok", "article": {"kb_id": "APX-KB-0105", "topic": "Payments", "error_code": "APX-4305", "surface": "Website", "symptom": "Coupon code is rejected with \"APX-4305: coupon not applicable\".", "cause": "The cart contains a category that is excluded from the coupon, or the coupon expired at 
- `support_agent`: I am sorry to hear you are having trouble applying your coupon. This is often related to error code APX-4305, which usually means the items in your cart are excluded from the coupon's terms or the coupon has expired.

To help us figure this out, could you please check the following:
1. Does your cart contain any grocery subscriptions or items that are only available via EMI? These are typically excluded from most coupons.
2. Please double-check the expiry date on the coupon you are trying to use.

If you are still seeing the error after checking these, please let me know, and we can look into 
state: {}
