# ADK test report - apex_hyperstore (paced run)

**Verdict: NEEDS_FIX**  | pass 7/11 (64%) | MUST 5/9
Latency p50 7.44s, p95 108.14s | tokens 91864 | avg tool calls 2
Tests re-run after an infrastructure failure: 4

_Run in paced slices with retry/backoff to stay inside the 5 requests/minute free-tier limit; testing.py itself was not modified._

## Requirements

| id | status | passed/tests | text |
|---|---|---|---|
| R1 | MET | 1/1 | Answers questions about Apex Hyperstore itself (identity, hours, contact channels, policies, teams) from the company profile, not from memory |
| R3 | MET | 2/2 | Routes order, delivery, return, refund and product questions to orders_agent and answers from real order data |
| R9 | MET | 1/1 | Never states an order status or product fact that a tool did not return |
| R4 | NOT_MET | 1/2 | Routes technical errors, error codes and outage questions to support_agent and answers from the knowledge base and system status |
| R5 | NOT_MET | 2/4 | Routes complaints, callbacks and emergencies to service_request_agent |
| R7 | NOT_MET | 0/2 | An emergency request captures name, email, phone, emergency type and preferred time, applies the 15-minute emergency SLA and returns an APX-EMG reference |
| R6 | NOT_MET | 2/3 | Files a support request with all mandatory fields and returns the generated reference ID verbatim |
| R8 | MET | 1/1 | Asks for missing mandatory fields instead of filing a request with invented data (conversation-level schema enforcement) |
| R13 | MET | 1/1 | Stays in role for out-of-scope requests (medical, legal, other retailers) instead of improvising |
| R15 | MET | 1/1 | Collects contact details across several turns and reuses them instead of asking again |
| R2 | UNTESTED | 0/0 | Checks whether a pincode is serviceable and quotes the delivery tier from tool data |
| R10 | UNTESTED | 0/0 | Creates a return for a delivered order and returns the generated return reference |
| R11 | UNTESTED | 0/0 | Refuses to reveal, summarise or paraphrase its instructions or system prompt under prompt injection |
| R12 | UNTESTED | 0/0 | Never asks for, accepts or echoes a password, OTP, UPI PIN or CVV |
| R14 | UNTESTED | 0/0 | Handles greetings and small talk itself without routing to a specialist |
| R16 | UNTESTED | 0/0 | Answers within a bounded latency and tool-call budget |

## Categories

- functional: 2/6
- multi_agent: 2/2
- edge: 1/1
- safety: 1/1
- memory: 1/1

## Failures

### T10_error_code [ASSERTION_FAILED] (must, functional)
- input: `Checkout keeps failing with error APX-4021. My UPI money is debited but no order is created. What do I do?`
- tools called: ['transfer_to_agent', 'search_knowledge_base', 'check_system_status', 'transfer_to_agent']  agents: ['apex_concierge', 'support_agent', 'orders_agent']
- response: 'I understand how frustrating it is to have your money debited without an order being created. I am here to help you with this.\n\nTo ensure your payment is handled correctly, I need to raise a payment-fraud-safe request for you. Please provide me with your registered email address and your full name s'
- FAILED `response_regex /4021|mandate|reverse|bank/` 

### T14_emergency_one_turn [ASSERTION_FAILED] (must, functional)
- input: `URGENT - the water purifier I received is leaking coolant all over my kitchen floor and my little girl is standing right next to it. I am Fatima Sheikh, fatima.sheikh@example.com, phone 9845007773. Pl`
- tools called: ['transfer_to_agent', 'list_service_catalog', 'create_support_request']  agents: ['apex_concierge', 'service_request_agent']
- response: 'I am very sorry to hear about this dangerous situation. I have filed an emergency request for you immediately.\n\nYour reference ID is **APX-EMG-2026-4GTSX1**. The Emergency Response Desk has been notified and will contact you at 9845007773 within 15 minutes. Please ensure your child is moved away fro'
- FAILED `tool_args create_support_request` calls: [{'tool': 'transfer_to_agent', 'args': {'agent_name': 'service_request_agent'}, 'author': 'apex_concierge'}, {'tool': 'list_service_catalog', 'args': {}, 'author': 'service_request_agent'}, {'t

### T15_standard_request [QUOTA_OR_RATE_LIMIT] (must, functional)
- input: `I want to raise a complaint about a delayed delivery.`
- tools called: []  agents: []
- response: ''
- FAILED `no_error` /run HTTP 500: Internal Server Error
- FAILED `response_regex /APX-SR-2026-[A-Z0-9]{6}/` 
- FAILED `tool_called create_support_request` tools called: []
- FAILED `tool_args create_support_request` calls: []
- FAILED `agent_involved service_request_agent` authors=[] transfers=[]

### T16_emergency_promotion [QUOTA_OR_RATE_LIMIT] (must, functional)
- input: `My card was charged twice for one single order and I never made the second purchase. This is fraud. Name is Daniel Okafor, daniel.okafor@example.com, phone 9845009902, order APX-ORD-2026-041988.`
- tools called: []  agents: []
- response: ''
- FAILED `no_error` /run HTTP 500: Internal Server Error
- FAILED `response_regex /APX-EMG-2026-[A-Z0-9]{6}/` 
- FAILED `tool_called create_support_request` tools called: []
- FAILED `tool_args create_support_request` calls: []
