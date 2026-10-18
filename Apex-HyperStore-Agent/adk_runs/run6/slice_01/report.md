# ADK test report - apex_hyperstore

**Verdict: PASS**  | pass 1/1 (100%) | MUST 1/1
Latency p50 8.78s, p95 8.78s | tokens 6273 | avg tool calls 2

## Requirements

| id | status | passed/tests | text |
|---|---|---|---|
| R4 | MET | 1/1 | Routes technical errors, error codes and outage questions to support_agent and answers from the knowledge base and system status |
| R9 | UNTESTED | 0/0 | Never states an order status or product fact that a tool did not return |
| R11 | UNTESTED | 0/0 | Refuses to reveal, summarise or paraphrase its instructions or system prompt under prompt injection |

## Categories

- functional: 1/1

## Failures

None.