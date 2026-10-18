# Transcripts - apex_hyperstore

## T18_route_support - PASS
**user:** The Apex app crashes with a blank screen every time I open My Orders on Android.
- `apex_concierge` -> tool `transfer_to_agent` {"agent_name": "support_agent"}
- tool result `transfer_to_agent`: {"result": null}
- `support_agent` -> tool `search_knowledge_base` {"query": "app crashes blank screen My Orders Android"}
- tool result `search_knowledge_base`: {"status": "ok", "query": "app crashes blank screen My Orders Android", "count": 3, "articles": [{"kb_id": "APX-KB-0102", "topic": "Delivery tracking", "error_code": "APX-4099", "surface": "Apex app", "symptom": "Tracking page shows \"Out for delivery\" for more than 24 hours and never updates.", "c
- `support_agent` -> tool `search_knowledge_base` {"query": "crash"}
- tool result `search_knowledge_base`: {"status": "no_match", "query": "crash", "message": "No article matches. Ask for the exact error code shown on screen, or file a request with the support agent."}
- `support_agent` -> tool `transfer_to_agent` {"agent_name": "service_request_agent"}
- tool result `transfer_to_agent`: {"result": null}
- `service_request_agent` -> tool `transfer_to_agent` {"agent_name": "support_agent"}
- tool result `transfer_to_agent`: {"result": null}
- `support_agent`: I am sorry for the trouble you are experiencing with the Apex app crashing on Android when you open My Orders. We do not have a specific troubleshooting guide for that exact error in our knowledge base. 

Let us open a service request so our technical team can investigate this for you right away. Would you like me to connect you with our service request team to set that up?
state: {}
