# ADK test report - apex_hyperstore

**Verdict: NEEDS_FIX**  | pass 2/3 (67%) | MUST 2/3
Latency p50 19.5s, p95 20.04s | tokens 29428 | avg tool calls 3

## Requirements

| id | status | passed/tests | text |
|---|---|---|---|
| R4 | NOT_MET | 2/3 | Routes technical errors, error codes and outage questions to support_agent and answers from the knowledge base and system status |
| R1 | UNTESTED | 0/0 | Answers questions about Apex Hyperstore itself (identity, hours, contact channels, policies, teams) from the company profile, not from memory |
| R2 | UNTESTED | 0/0 | Checks whether a pincode is serviceable and quotes the delivery tier from tool data |
| R3 | UNTESTED | 0/0 | Routes order, delivery, return, refund and product questions to orders_agent and answers from real order data |
| R5 | UNTESTED | 0/0 | Routes complaints, callbacks and emergencies to service_request_agent |
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

- functional: 2/3

## Failures

### T10_error_code [ASSERTION_FAILED] (must, functional)
- input: `Checkout keeps failing with error APX-4021. My UPI money is debited but no order is created. What do I do?`
- tools called: ['transfer_to_agent', 'search_knowledge_base', 'check_system_status', 'transfer_to_agent']  agents: ['apex_concierge', 'support_agent', 'orders_agent']
- response: 'I understand how frustrating it is to have your money debited without an order being created. I am here to help you get this resolved.\n\nSince our payment systems are currently experiencing some latency, please check your bank app to see if there is a pending mandate. If you find one, please reverse '
- FAILED `agent_excluded orders_agent` authors=['apex_concierge', 'support_agent', 'orders_agent']  
  hint: A sub-agent handled a request it should not. Sharpen descriptions to remove overlap.
