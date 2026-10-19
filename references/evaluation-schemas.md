# ADK Evaluation & Conformance Schemas Reference

## 1. `EvalSet` and `EvalCase` Schema (`*.evalset.json` / `*.test.json`)

```json
{
  "eval_set_id": "order_agent_eval_set",
  "name": "Order Agent Regression Suite",
  "description": "Verifies tool trajectory and final response quality.",
  "eval_cases": [
    {
      "eval_id": "case_01_lookup",
      "conversation": [
        {
          "invocation_id": "inv-001",
          "user_content": {
            "role": "user",
            "parts": [{"text": "check status of item 101"}]
          },
          "final_response": {
            "role": "model",
            "parts": [{"text": "Verified domain lookup result for: check status of item 101"}]
          },
          "intermediate_data": {
            "tool_uses": [
              {
                "name": "execute_domain_lookup",
                "args": {"query": "check status of item 101"}
              }
            ],
            "intermediate_responses": []
          }
        }
      ],
      "session_input": {
        "app_name": "order_agent",
        "user_id": "test_user",
        "state": {}
      }
    }
  ]
}
```

## 2. Evaluation Criteria (`test_config.json`)

- **Deterministic CI Criteria**:
  - `tool_trajectory_avg_score` (default `1.0`, supports `ignore_args` in ADK v2.9.0+)
  - `response_match_score` (ROUGE-1 similarity, default `0.8`)
- **LLM-as-Judge Criteria** (require `GEMINI_API_KEY` or Vertex AI credentials in live mode):
  - `final_response_match_v2`, `rubric_based_final_response_quality_v1`, `rubric_based_tool_use_quality_v1`, `hallucinations_v1`, `safety_v1`, `multi_turn_task_success_v1`.
- **Automatic Efficiency Metrics** (ADK v2.10.0+):
  - `tool_call_count_v1`, `inference_call_count_v1`, `token_usage_v1`, `invocation_duration_v1`.
