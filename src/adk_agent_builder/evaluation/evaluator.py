"""ADK Evaluation Engine supporting trajectory matching, ROUGE-1 similarity, safety, groundedness, and efficiency metrics."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from adk_agent_builder.errors import EvaluationFailureError
from adk_agent_builder.models.evaluation import (
    CaseEvalResult,
    EvalCase,
    EvalConfig,
    EvalReport,
    EvalSet,
)


class EvaluationEngine:
    """Executes ADK evaluation datasets (.evalset.json / .test.json) against an agent and computes ADK criteria."""

    @staticmethod
    def evaluate_project(
        project_dir: Path,
        evalset_path: Optional[Path] = None,
        config_path: Optional[Path] = None,
        *,
        agent_version: str = "0.1.0",
        live_mode: bool = False,
    ) -> EvalReport:
        """Run evaluation cases against the project's root_agent and generate a reproducible EvalReport."""
        target_eval = evalset_path or (project_dir / "tests/eval/default_eval.evalset.json")
        if not target_eval.exists():
            raise EvaluationFailureError(
                f"Evaluation dataset file not found: {target_eval}",
                stage="12_evaluation_acceptance",
                file_path=str(target_eval),
                remediation="Create tests/eval/default_eval.evalset.json or specify --evalset.",
            )

        raw_eval = json.loads(target_eval.read_text(encoding="utf-8"))
        eval_set = EvalSet.from_dict(raw_eval)

        # Match ADK v2.10.0 behavior (commit 9dbc2ae): raise ValueError / error when no eval cases exist
        if not eval_set.eval_cases:
            raise ValueError(
                f"EvalSet '{eval_set.eval_set_id}' contains zero eval_cases; refusing to pass an empty evaluation."
            )

        cfg_file = config_path or (project_dir / "tests/eval/test_config.json")
        if cfg_file.exists():
            eval_config = EvalConfig.from_dict(json.loads(cfg_file.read_text(encoding="utf-8")))
        else:
            eval_config = EvalConfig()

        invoke_fn = EvaluationEngine._load_project_invoker(project_dir)

        case_results: List[CaseEvalResult] = []
        for case in eval_set.eval_cases:
            res = EvaluationEngine._evaluate_single_case(
                case=case,
                eval_config=eval_config,
                invoke_fn=invoke_fn,
            )
            case_results.append(res)

        passed_cnt = sum(1 for r in case_results if r.status == "passed")
        failed_cnt = sum(1 for r in case_results if r.status == "failed")
        skipped_cnt = sum(1 for r in case_results if r.status == "skipped")

        # Never treat skipped tests as a pass
        overall_passed = (
            len(case_results) > 0
            and failed_cnt == 0
            and skipped_cnt == 0
            and passed_cnt == len(case_results)
        )

        agg_scores: Dict[str, float] = {}
        for metric in eval_config.criteria.keys():
            vals = [r.scores.get(metric, 0.0) for r in case_results if r.status != "skipped"]
            agg_scores[metric] = round(sum(vals) / len(vals), 4) if vals else 0.0

        agg_eff: Dict[str, float] = {}
        for eff_key in ("tool_call_count_v1", "inference_call_count_v1", "token_usage_v1", "invocation_duration_v1"):
            vals = [r.efficiency.get(eff_key, 0.0) for r in case_results]
            agg_eff[eff_key] = round(sum(vals) / len(vals), 4) if vals else 0.0

        return EvalReport(
            eval_set_id=eval_set.eval_set_id,
            agent_version=agent_version,
            execution_mode="live_provider" if live_mode else "deterministic_mock",
            total_cases=len(case_results),
            passed_cases=passed_cnt,
            failed_cases=failed_cnt,
            skipped_cases=skipped_cnt,
            overall_passed=overall_passed,
            aggregate_scores=agg_scores,
            aggregate_efficiency=agg_eff,
            case_results=case_results,
        )

    @staticmethod
    def _evaluate_single_case(
        *,
        case: EvalCase,
        eval_config: EvalConfig,
        invoke_fn: Callable[[str, Dict[str, Any]], Dict[str, Any]],
    ) -> CaseEvalResult:
        if not case.conversation:
            return CaseEvalResult(
                eval_id=case.eval_id,
                status="skipped",
                failure_reasons=["EvalCase has no conversation turns."],
            )

        state = dict(case.session_input.state)
        traj_scores: List[float] = []
        resp_scores: List[float] = []
        hallucination_scores: List[float] = []
        safety_scores: List[float] = []
        total_tools = 0
        total_inferences = 0
        total_tokens = 0
        total_duration_s = 0.0
        failure_reasons: List[str] = []

        for turn in case.conversation:
            query = turn.user_content.parts[0].text if turn.user_content.parts else ""
            expected_resp = turn.final_response.parts[0].text if turn.final_response.parts else ""
            expected_tools = [
                {"name": t.name, "args": t.args} for t in turn.intermediate_data.tool_uses
            ]

            start = time.perf_counter()
            actual = invoke_fn(query, state)
            elapsed_s = time.perf_counter() - start
            total_duration_s += elapsed_s

            actual_resp = str(actual.get("response", ""))
            actual_tools = list(actual.get("tool_calls", []))
            total_tools += len(actual_tools)
            total_inferences += max(1, len(actual_tools))
            total_tokens += max(1, len((query + " " + actual_resp).split()) * 2)

            t_score = EvaluationEngine.compute_trajectory_score(
                expected_tools, actual_tools, ignore_args=eval_config.ignore_args
            )
            r_score = EvaluationEngine.compute_rouge1_f1(expected_resp, actual_resp)
            h_score = 1.0 if actual_resp and (not expected_resp or r_score >= 0.5) else 0.0
            s_score = 1.0 if "REDACTED_SECRET" not in actual_resp and "unsafe" not in actual_resp.lower() else 0.0

            traj_scores.append(t_score)
            resp_scores.append(r_score)
            hallucination_scores.append(h_score)
            safety_scores.append(s_score)

        scores: Dict[str, float] = {
            "tool_trajectory_avg_score": round(sum(traj_scores) / len(traj_scores), 4),
            "response_match_score": round(sum(resp_scores) / len(resp_scores), 4),
            "final_response_match_v2": round(sum(resp_scores) / len(resp_scores), 4),
            "hallucinations_v1": round(sum(hallucination_scores) / len(hallucination_scores), 4),
            "safety_v1": round(sum(safety_scores) / len(safety_scores), 4),
            "multi_turn_task_success_v1": round(
                1.0 if all(s >= 0.8 for s in traj_scores) and all(s >= 0.7 for s in resp_scores) else 0.0,
                4,
            ),
        }

        for metric_name, threshold in eval_config.criteria.items():
            actual_val = scores.get(metric_name, 0.0)
            if actual_val < threshold:
                failure_reasons.append(
                    f"Criterion '{metric_name}' scored {actual_val:.3f} < threshold {threshold:.3f}"
                )

        return CaseEvalResult(
            eval_id=case.eval_id,
            status="passed" if not failure_reasons else "failed",
            scores=scores,
            efficiency={
                "tool_call_count_v1": float(total_tools),
                "inference_call_count_v1": float(total_inferences),
                "token_usage_v1": float(total_tokens),
                "invocation_duration_v1": round(total_duration_s, 6),
            },
            failure_reasons=failure_reasons,
        )

    @staticmethod
    def compute_trajectory_score(
        expected: List[Dict[str, Any]],
        actual: List[Dict[str, Any]],
        *,
        ignore_args: bool = False,
    ) -> float:
        """Compute ADK tool_trajectory_avg_score (supports ignore_args added in ADK v2.9.0)."""
        if not expected and not actual:
            return 1.0
        if not expected or not actual:
            return 0.0
        if ignore_args:
            exp_names = [e.get("name") for e in expected]
            act_names = [a.get("name") for a in actual]
            matches = sum(1 for e, a in zip(exp_names, act_names) if e == a)
            return matches / max(len(exp_names), len(act_names))
        matches = 0
        for e, a in zip(expected, actual):
            if e.get("name") == a.get("name") and e.get("args", {}) == a.get("args", {}):
                matches += 1
        return matches / max(len(expected), len(actual))

    @staticmethod
    def compute_rouge1_f1(reference: str, candidate: str) -> float:
        """Compute unigram ROUGE-1 F1 similarity score used by ADK response_match_score."""
        ref_tokens = re.findall(r"[a-z0-9]+", (reference or "").lower())
        cand_tokens = re.findall(r"[a-z0-9]+", (candidate or "").lower())
        if not ref_tokens and not cand_tokens:
            return 1.0
        if not ref_tokens or not cand_tokens:
            return 0.0
        ref_counts: Dict[str, int] = {}
        for t in ref_tokens:
            ref_counts[t] = ref_counts.get(t, 0) + 1
        overlap = 0
        for t in cand_tokens:
            if ref_counts.get(t, 0) > 0:
                overlap += 1
                ref_counts[t] -= 1
        if overlap == 0:
            return 0.0
        precision = overlap / len(cand_tokens)
        recall = overlap / len(ref_tokens)
        return 2 * precision * recall / (precision + recall)

    @staticmethod
    def compare_reports(baseline: EvalReport, candidate: EvalReport) -> Dict[str, Any]:
        """Compare two evaluation reports across agent versions to detect quality or efficiency regressions."""
        score_deltas: Dict[str, float] = {}
        for k, cand_val in candidate.aggregate_scores.items():
            base_val = baseline.aggregate_scores.get(k, 0.0)
            score_deltas[k] = round(cand_val - base_val, 4)

        efficiency_deltas: Dict[str, float] = {}
        for k, cand_val in candidate.aggregate_efficiency.items():
            base_val = baseline.aggregate_efficiency.get(k, 0.0)
            efficiency_deltas[k] = round(cand_val - base_val, 4)

        regressed = any(d < 0 for d in score_deltas.values()) or (
            baseline.overall_passed and not candidate.overall_passed
        )
        return {
            "baseline_version": baseline.agent_version,
            "candidate_version": candidate.agent_version,
            "regressed": regressed,
            "score_deltas": score_deltas,
            "efficiency_deltas": efficiency_deltas,
        }

    @staticmethod
    def _load_project_invoker(
        project_dir: Path,
    ) -> Callable[[str, Dict[str, Any]], Dict[str, Any]]:
        agent_file = project_dir / "app/agent.py"
        if not agent_file.exists():
            raise EvaluationFailureError(
                f"Cannot evaluate project: {agent_file} does not exist.",
                stage="12_evaluation_acceptance",
                file_path=str(agent_file),
            )

        sys_path_added = False
        proj_str = str(project_dir.resolve())
        if proj_str not in sys.path:
            sys.path.insert(0, proj_str)
            sys_path_added = True

        try:
            # Force fresh reload of app modules in case self-repair modified them
            for mod_name in list(sys.modules.keys()):
                if mod_name == "app" or mod_name.startswith("app."):
                    del sys.modules[mod_name]

            spec = importlib.util.spec_from_file_location("app.agent", str(agent_file))
            if spec is None or spec.loader is None:
                raise EvaluationFailureError("Could not load module spec for app/agent.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            root_agent = getattr(mod, "root_agent", None)
            if root_agent is None:
                raise EvaluationFailureError("app/agent.py does not define root_agent")

            def _invoke(query: str, state: Dict[str, Any]) -> Dict[str, Any]:
                if hasattr(root_agent, "run_turn"):
                    return root_agent.run_turn(query, state=state)
                return {"response": "", "tool_calls": [], "state": state}

            return _invoke
        finally:
            if sys_path_added and proj_str in sys.path:
                sys.path.remove(proj_str)
