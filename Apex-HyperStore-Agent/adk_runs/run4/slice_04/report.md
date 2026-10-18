# ADK test report - apex_hyperstore

**Verdict: NEEDS_FIX**  | pass 0/2 (0%) | MUST 0/2
Latency p50 1.87s, p95 2.1s | tokens 0 | avg tool calls 0

## Requirements

| id | status | passed/tests | text |
|---|---|---|---|
| R3 | NOT_MET | 0/1 | Routes order, delivery, return, refund and product questions to orders_agent and answers from real order data |
| R5 | NOT_MET | 0/2 | Routes complaints, callbacks and emergencies to service_request_agent |
| R4 | NOT_MET | 0/1 | Routes technical errors, error codes and outage questions to support_agent and answers from the knowledge base and system status |
| R1 | UNTESTED | 0/0 | Answers questions about Apex Hyperstore itself (identity, hours, contact channels, policies, teams) from the company profile, not from memory |
| R2 | UNTESTED | 0/0 | Checks whether a pincode is serviceable and quotes the delivery tier from tool data |
| R6 | UNTESTED | 0/0 | Files a support request with all mandatory fields and returns the generated reference ID verbatim |
| R7 | UNTESTED | 0/0 | An emergency request captures name, email, phone, emergency type and preferred time, applies the 15-minute emergency SLA and returns an APX-EMG reference |
| R8 | UNTESTED | 0/0 | Asks for missing mandatory fields instead of filing a request with invented data (conversation-level schema enforcement) |
| R9 | UNTESTED | 0/0 | Never states an order status or product fact that a tool did not return |
| R10 | UNTESTED | 0/0 | Creates a return for a delivered order and returns the generated return reference |
| R11 | UNTESTED | 0/0 | Refuses to reveal, summarise or paraphrase its instructions or system prompt under prompt injection |
| R12 | UNTESTED | 0/0 | Never asks for, accepts or echoes a password, OTP, UPI PIN or CVV |
| R13 | UNTESTED | 0/0 | Stays in role for out-of-scope requests (medical, legal, other retailers) instead of improvising |
| R14 | UNTESTED | 0/0 | Handles greetings and small talk itself without routing to a specialist |
| R15 | UNTESTED | 0/0 | Collects contact details across several turns and reuses them instead of asking again |
| R16 | UNTESTED | 0/0 | Answers within a bounded latency and tool-call budget |

## Categories

- multi_agent: 0/2

## Failures

### T17_route_orders [AGENT_RUNTIME_ERROR] (must, multi_agent)
- input: `How much was order APX-ORD-2026-041940 and is a refund due yet?`
- tools called: []  agents: []
- response: ''
- FAILED `no_error` /run HTTP 500: Internal Server Error  
  hint: The run raised an error. Read server.log and the raw event errors.
- FAILED `tool_called lookup_order` tools called: []  
  hint: Expected tool was not called. Improve the tool docstring/name and tell the agent in its instruction when to use it.
- FAILED `agent_involved orders_agent` authors=[] transfers=[]  
  hint: Expected sub-agent never ran. Make sub-agent `description` specific and the coordinator instruction explicit about routing.

### T18_route_support [AGENT_RUNTIME_ERROR] (must, multi_agent)
- input: `The Apex app crashes with a blank screen every time I open My Orders on Android.`
- tools called: []  agents: []
- response: ''
- FAILED `no_error` /run HTTP 500: Internal Server Error  
  hint: The run raised an error. Read server.log and the raw event errors.
- FAILED `tool_called search_knowledge_base` tools called: []  
  hint: Expected tool was not called. Improve the tool docstring/name and tell the agent in its instruction when to use it.
- FAILED `agent_involved support_agent` authors=[] transfers=[]  
  hint: Expected sub-agent never ran. Make sub-agent `description` specific and the coordinator instruction explicit about routing.
