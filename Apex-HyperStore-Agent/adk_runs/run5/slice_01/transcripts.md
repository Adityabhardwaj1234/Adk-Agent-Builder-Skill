# Transcripts - apex_hyperstore

## T10_error_code - PASS
**user:** Checkout keeps failing with error APX-4021. My UPI money is debited but no order is created. What do I do?
- `apex_concierge` -> tool `transfer_to_agent` {"agent_name": "support_agent"}
- tool result `transfer_to_agent`: {"result": null}
- `support_agent` -> tool `search_knowledge_base` {"query": "APX-4021"}
- tool result `search_knowledge_base`: {"status": "ok", "query": "APX-4021", "count": 3, "articles": [{"kb_id": "APX-KB-0101", "topic": "Checkout", "error_code": "APX-4021", "surface": "Apex app / website", "symptom": "\"Payment failed (APX-4021)\" at checkout although UPI request was debited.", "cause": "UPI mandate succeeded at the ban
- `support_agent` -> tool `get_troubleshooting_guide` {"kb_id": "APX-KB-0101"}
- tool result `get_troubleshooting_guide`: {"status": "ok", "article": {"kb_id": "APX-KB-0101", "topic": "Checkout", "error_code": "APX-4021", "surface": "Apex app / website", "symptom": "\"Payment failed (APX-4021)\" at checkout although UPI request was debited.", "cause": "UPI mandate succeeded at the bank but the payment-gateway callback 
- `support_agent`: Error APX-4021 happens when your UPI payment succeeds at your bank, but the payment gateway's callback to us times out before your order can be created. 

Please follow these steps to resolve it:
1. Check your bank app to see if there is a pending mandate, and reverse it if present.
2. Retry your checkout using the same UPI handle on a new payment attempt. 

Please note: we will never ask you to share a UPI PIN, OTP, or CVV. Did this help complete your order, or has the debit repeated?
state: {}
