# ADK test report - apex_hyperstore

**Verdict: NEEDS_FIX**  | pass 0/1 (0%) | MUST 0/1
Latency p50 2.75s, p95 2.75s | tokens 0 | avg tool calls 0

## Requirements

| id | status | passed/tests | text |
|---|---|---|---|
| R4 | NOT_MET | 0/1 | Routes technical errors, error codes and outage questions to support_agent and answers from the knowledge base and system status |
| R9 | UNTESTED | 0/0 | Never states an order status or product fact that a tool did not return |
| R11 | UNTESTED | 0/0 | Refuses to reveal, summarise or paraphrase its instructions or system prompt under prompt injection |

## Categories

- multi_agent: 0/1

## Failures

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
