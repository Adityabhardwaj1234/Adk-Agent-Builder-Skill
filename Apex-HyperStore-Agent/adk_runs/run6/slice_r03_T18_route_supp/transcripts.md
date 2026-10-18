# Transcripts - apex_hyperstore

## T18_route_support - PASS
**user:** The Apex app crashes with a blank screen every time I open My Orders on Android.
- `apex_concierge` -> tool `transfer_to_agent` {"agent_name": "support_agent"}
- tool result `transfer_to_agent`: {"result": null}
- `support_agent` -> tool `search_knowledge_base` {"query": "app crashes blank screen My Orders Android"}
- tool result `search_knowledge_base`: {"status": "ok", "query": "app crashes blank screen My Orders Android", "count": 3, "articles": [{"kb_id": "APX-KB-0102", "topic": "Delivery tracking", "error_code": "APX-4099", "surface": "Apex app", "symptom": "Tracking page shows \"Out for delivery\" for more than 24 hours and never updates.", "c
- `support_agent` -> tool `search_knowledge_base` {"query": "app crashes"}
- tool result `search_knowledge_base`: {"status": "ok", "query": "app crashes", "count": 3, "articles": [{"kb_id": "APX-KB-0105", "topic": "Payments", "error_code": "APX-4305", "surface": "Website", "symptom": "Coupon code is rejected with \"APX-4305: coupon not applicable\".", "cause": "The cart contains a category that is excluded from
- `support_agent` -> tool `search_knowledge_base` {"query": "crash"}
- tool result `search_knowledge_base`: {"status": "no_match", "query": "crash", "message": "No article matches. Ask for the exact error code shown on screen, or file a request with the support agent."}
- `support_agent`: I am sorry to hear that the Apex app is crashing when you open My Orders on Android. We could not find a specific troubleshooting guide for that exact crash in our knowledge base. 

Could you please share a screenshot or the exact wording of any error message shown on the screen? If this persists, I would be happy to register a request for our technical support team to investigate further.
state: {}
