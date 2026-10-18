# ADK test report - apex_hyperstore

**Verdict: NEEDS_FIX**  | pass 2/3 (67%) | MUST 1/2
Latency p50 5.93s, p95 10.3s | tokens 18364 | avg tool calls 1.33

## Requirements

| id | status | passed/tests | text |
|---|---|---|---|
| R5 | MET | 1/1 | Routes complaints, callbacks and emergencies to service_request_agent |
| R6 | NOT_MET | 1/2 | Files a support request with all mandatory fields and returns the generated reference ID verbatim |
| R14 | MET | 1/1 | Handles greetings and small talk itself without routing to a specialist |
| R8 | NOT_MET | 0/1 | Asks for missing mandatory fields instead of filing a request with invented data (conversation-level schema enforcement) |
| R1 | UNTESTED | 0/0 | Answers questions about Apex Hyperstore itself (identity, hours, contact channels, policies, teams) from the company profile, not from memory |
| R2 | UNTESTED | 0/0 | Checks whether a pincode is serviceable and quotes the delivery tier from tool data |
| R3 | UNTESTED | 0/0 | Routes order, delivery, return, refund and product questions to orders_agent and answers from real order data |
| R4 | UNTESTED | 0/0 | Routes technical errors, error codes and outage questions to support_agent and answers from the knowledge base and system status |
| R7 | UNTESTED | 0/0 | An emergency request captures name, email, phone, emergency type and preferred time, applies the 15-minute emergency SLA and returns an APX-EMG reference |
| R9 | UNTESTED | 0/0 | Never states an order status or product fact that a tool did not return |
| R10 | UNTESTED | 0/0 | Creates a return for a delivered order and returns the generated return reference |
| R11 | UNTESTED | 0/0 | Refuses to reveal, summarise or paraphrase its instructions or system prompt under prompt injection |
| R12 | UNTESTED | 0/0 | Never asks for, accepts or echoes a password, OTP, UPI PIN or CVV |
| R13 | UNTESTED | 0/0 | Stays in role for out-of-scope requests (medical, legal, other retailers) instead of improvising |
| R15 | UNTESTED | 0/0 | Collects contact details across several turns and reuses them instead of asking again |
| R16 | UNTESTED | 0/0 | Answers within a bounded latency and tool-call budget |

## Categories

- multi_agent: 2/2
- edge: 0/1

## Failures

### T21_missing_fields [ASSERTION_FAILED] (must, edge)
- input: `Nobody delivered my grocery order and I am very upset. Please fix this.`
- tools called: ['transfer_to_agent']  agents: ['apex_concierge', 'orders_agent']
- response: "I understand you're frustrated that your grocery order hasn't arrived yet, and we want to get this sorted out for you right away. Could you please share your order ID and your registered email address so we can look into the delivery status?"
- FAILED `agent_involved service_request_agent` authors=['apex_concierge', 'orders_agent'] transfers=['orders_agent']  
  hint: Expected sub-agent never ran. Make sub-agent `description` specific and the coordinator instruction explicit about routing.
