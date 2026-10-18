# ADK test report - apex_hyperstore

**Verdict: NEEDS_FIX**  | pass 2/3 (67%) | MUST 2/3
Latency p50 7.19s, p95 15.92s | tokens 9675 | avg tool calls 0.67

## Requirements

| id | status | passed/tests | text |
|---|---|---|---|
| R1 | MET | 1/1 | Answers questions about Apex Hyperstore itself (identity, hours, contact channels, policies, teams) from the company profile, not from memory |
| R2 | MET | 1/1 | Checks whether a pincode is serviceable and quotes the delivery tier from tool data |
| R3 | NOT_MET | 0/1 | Routes order, delivery, return, refund and product questions to orders_agent and answers from real order data |
| R9 | NOT_MET | 0/1 | Never states an order status or product fact that a tool did not return |
| R4 | UNTESTED | 0/0 | Routes technical errors, error codes and outage questions to support_agent and answers from the knowledge base and system status |
| R5 | UNTESTED | 0/0 | Routes complaints, callbacks and emergencies to service_request_agent |
| R6 | UNTESTED | 0/0 | Files a support request with all mandatory fields and returns the generated reference ID verbatim |
| R7 | UNTESTED | 0/0 | An emergency request captures name, email, phone, emergency type and preferred time, applies the 15-minute emergency SLA and returns an APX-EMG reference |
| R8 | UNTESTED | 0/0 | Asks for missing mandatory fields instead of filing a request with invented data (conversation-level schema enforcement) |
| R10 | UNTESTED | 0/0 | Creates a return for a delivered order and returns the generated return reference |
| R11 | UNTESTED | 0/0 | Refuses to reveal, summarise or paraphrase its instructions or system prompt under prompt injection |
| R12 | UNTESTED | 0/0 | Never asks for, accepts or echoes a password, OTP, UPI PIN or CVV |
| R13 | UNTESTED | 0/0 | Stays in role for out-of-scope requests (medical, legal, other retailers) instead of improvising |
| R14 | UNTESTED | 0/0 | Handles greetings and small talk itself without routing to a specialist |
| R15 | UNTESTED | 0/0 | Collects contact details across several turns and reuses them instead of asking again |
| R16 | UNTESTED | 0/0 | Answers within a bounded latency and tool-call budget |

## Categories

- functional: 2/3

## Failures

### T06_order_status [AGENT_RUNTIME_ERROR] (must, functional)
- input: `Where is my order APX-ORD-2026-041882? Please tell me the status and delivery slot.`
- tools called: []  agents: []
- response: ''
- FAILED `no_error` /run HTTP 500: Internal Server Error  
  hint: The run raised an error. Read server.log and the raw event errors.
- FAILED `response_regex /out for delivery|APX-ORD-2026-041882/` 
- FAILED `tool_called lookup_order` tools called: []  
  hint: Expected tool was not called. Improve the tool docstring/name and tell the agent in its instruction when to use it.
- FAILED `tool_args lookup_order` calls: []  
  hint: Tool called with unexpected arguments. Simplify the signature, add type hints and parameter docs.
- FAILED `agent_involved orders_agent` authors=[] transfers=[]  
  hint: Expected sub-agent never ran. Make sub-agent `description` specific and the coordinator instruction explicit about routing.
