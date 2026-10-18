# ADK test report - apex_hyperstore

**Verdict: PASS**  | pass 1/1 (100%) | MUST 1/1
Latency p50 8.73s, p95 8.73s | tokens 7195 | avg tool calls 2

## Requirements

| id | status | passed/tests | text |
|---|---|---|---|
| R3 | MET | 1/1 | Routes order, delivery, return, refund and product questions to orders_agent and answers from real order data |
| R5 | MET | 1/1 | Routes complaints, callbacks and emergencies to service_request_agent |
| R1 | UNTESTED | 0/0 | Answers questions about Apex Hyperstore itself (identity, hours, contact channels, policies, teams) from the company profile, not from memory |
| R2 | UNTESTED | 0/0 | Checks whether a pincode is serviceable and quotes the delivery tier from tool data |
| R4 | UNTESTED | 0/0 | Routes technical errors, error codes and outage questions to support_agent and answers from the knowledge base and system status |
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

- multi_agent: 1/1

## Failures

None.