"""Command-line interface (`adk-agent-builder`) covering the complete 17-stage lifecycle plus quota planning and HTML dashboards."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from adk_agent_builder import __version__
from adk_agent_builder.config import BuilderConfig
from adk_agent_builder.deployment.deployer import DeploymentManager
from adk_agent_builder.diagnostics.repair import DiagnosticsAndRepairEngine
from adk_agent_builder.errors import AdkBuilderError, ExitCode
from adk_agent_builder.evaluation.evaluator import EvaluationEngine
from adk_agent_builder.evaluation.quota import QuotaBudgetManager, QuotaBudgetPolicy
from adk_agent_builder.generation.generator import ProjectGenerator
from adk_agent_builder.integrations.adk_cli import AdkCliAdapter
from adk_agent_builder.models.lifecycle import EngineeringRunState, LifecycleStage, StageStatus
from adk_agent_builder.models.providers import PROVIDER_CATALOG
from adk_agent_builder.observability.dashboard import DashboardRenderer
from adk_agent_builder.observability.manager import ObservabilityConfig, ObservabilityManager
from adk_agent_builder.planning.planner import ArchitecturePlanner
from adk_agent_builder.requirements.engine import RequirementsEngine
from adk_agent_builder.security.scanner import SecurityScanner
from adk_agent_builder.skills.validator import SkillValidator
from adk_agent_builder.templates.catalog import list_templates
from adk_agent_builder.testing.runner import TestRunner
from adk_agent_builder.tools.registry import IntegrationRegistry
from adk_agent_builder.validation.validator import ProjectValidator


def _emit(payload: Dict[str, Any], as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    else:
        print(yaml.safe_dump(payload, sort_keys=False).strip())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="adk-agent-builder",
        description="Complete Google ADK Agent Creation, Validation, Testing, Evaluation, Quota Planning, and Deployment Suite",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--json", action="store_true", help="Emit structured JSON output")

    sub = parser.add_subparsers(dest="command", required=True)

    # 1. doctor
    p_doc = sub.add_parser("doctor", help="Inspect Python runtime, ADK/Agents CLI availability, and provider readiness")
    p_doc.add_argument("--json", action="store_true", help="Emit JSON output")

    # 2. audit
    p_aud = sub.add_parser("audit", help="Audit an existing ADK repository or project for structure, security, and health")
    p_aud.add_argument("--project-dir", default=".", help="Path to repository or project")
    p_aud.add_argument("--json", action="store_true", help="Emit JSON output")

    # 3. init
    p_init = sub.add_parser("init", help="Initialize a starter requirements specification file")
    p_init.add_argument("--name", default="my_adk_agent", help="Project name")
    p_init.add_argument("--objective", default="Help users look up domain records and verify compliance.", help="Business objective")
    p_init.add_argument("--output", default="requirements.yaml", help="Output YAML path")
    p_init.add_argument("--dry-run", action="store_true", help="Preview without writing file")
    p_init.add_argument("--json", action="store_true", help="Emit JSON output")

    # 4. requirements
    p_req = sub.add_parser("requirements", help="Parse, normalize, and validate customer requirements")
    p_req.add_argument("--spec", help="Path to YAML/JSON requirements file")
    p_req.add_argument("--from-text", help="Natural language requirement prompt")
    p_req.add_argument("--name", help="Optional project name override")
    p_req.add_argument("--output", help="Optional path to save normalized spec")
    p_req.add_argument("--json", action="store_true", help="Emit JSON output")

    # 5. plan
    p_plan = sub.add_parser("plan", help="Select optimal ADK architecture pattern and generate trade-off scorecard")
    p_plan.add_argument("--spec", required=True, help="Path to YAML/JSON requirements file")
    p_plan.add_argument("--output", help="Optional path to save architecture plan JSON/YAML")
    p_plan.add_argument("--json", action="store_true", help="Emit JSON output")

    # 6. build
    p_build = sub.add_parser("build", help="Generate complete ADK project from specification and run quality gates")
    p_build.add_argument("--spec", required=True, help="Path to YAML/JSON requirements file")
    p_build.add_argument("--output-dir", required=True, help="Destination project directory")
    p_build.add_argument("--repair", action="store_true", help="Enable bounded self-repair on failure")
    p_build.add_argument("--dry-run", action="store_true", help="Compute plan without writing files")
    p_build.add_argument("--json", action="store_true", help="Emit JSON output")

    # 7. validate
    p_val = sub.add_parser("validate", help="Run static, AST, entrypoint, schema, and security validation")
    p_val.add_argument("--project-dir", default=".", help="Target ADK project directory")
    p_val.add_argument("--repair", action="store_true", help="Run bounded self-repair if defects are found")
    p_val.add_argument("--json", action="store_true", help="Emit JSON output")

    # 8. test
    p_tst = sub.add_parser("test", help="Discover and execute project unit, integration, and contract tests")
    p_tst.add_argument("--project-dir", default=".", help="Target project directory")
    p_tst.add_argument("--subdir", help="Optional test subdirectory (e.g., tests/unit)")
    p_tst.add_argument("--timeout", type=int, default=60, help="Timeout in seconds")
    p_tst.add_argument("--json", action="store_true", help="Emit JSON output")

    # 9. eval
    p_eval = sub.add_parser("eval", help="Execute ADK evaluation sets (.evalset.json) and calculate criteria metrics")
    p_eval.add_argument("--project-dir", default=".", help="Target ADK project directory")
    p_eval.add_argument("--evalset", help="Optional path to .evalset.json or .test.json")
    p_eval.add_argument("--config", help="Optional path to test_config.json")
    p_eval.add_argument("--output", help="Optional path to write evaluation report JSON")
    p_eval.add_argument("--json", action="store_true", help="Emit JSON output")

    # 10. quota
    p_quota = sub.add_parser("quota", help="Estimate live API message cost and build a 20-messages/day safe slice plan")
    p_quota.add_argument("--spec", required=True, help="Path to spec.json or .evalset.json")
    p_quota.add_argument("--daily-limit", type=int, default=20, help="Daily message limit per model (default: 20)")
    p_quota.add_argument("--rpm-limit", type=int, default=5, help="Requests per minute limit (default: 5)")
    p_quota.add_argument("--slice-size", type=int, default=3, help="Cases per paced slice (default: 3)")
    p_quota.add_argument("--rotate-models", default="gemini-2.5-flash", help="Comma-separated models to rotate across slices")
    p_quota.add_argument("--ledger", help="Optional path to .adk_quota_ledger.json")
    p_quota.add_argument("--json", action="store_true", help="Emit JSON output")

    # 11. dashboard
    p_dash = sub.add_parser("dashboard", help="Render a standalone dark-mode HTML dashboard from results.json or EvalReport JSON")
    p_dash.add_argument("--input", required=True, help="Path to results.json or eval_report.json")
    p_dash.add_argument("--output", help="Output HTML file path (default: dashboard.html alongside input)")
    p_dash.add_argument("--evaluation-md", help="Optional qualitative markdown file to embed")
    p_dash.add_argument("--json", action="store_true", help="Emit JSON output")

    # 12. report
    p_rep = sub.add_parser("report", help="Generate comprehensive lifecycle, test, eval, and observability report")
    p_rep.add_argument("--project-dir", default=".", help="Target ADK project directory")
    p_rep.add_argument("--output", help="Optional output file path")
    p_rep.add_argument("--json", action="store_true", help="Emit JSON output")

    # 13. package
    p_pkg = sub.add_parser("package", help="Validate and package an ADK project into a clean distributable .zip archive")
    p_pkg.add_argument("--project-dir", default=".", help="Target ADK project directory")
    p_pkg.add_argument("--output", help="Destination .zip path")
    p_pkg.add_argument("--dry-run", action="store_true", help="Validate without creating archive")
    p_pkg.add_argument("--json", action="store_true", help="Emit JSON output")

    # 14. deploy
    p_dep = sub.add_parser("deploy", help="Validate prerequisites, audit .env secrets, and create/execute deployment plan")
    p_dep.add_argument("--project-dir", default=".", help="Target ADK project directory")
    p_dep.add_argument("--target", default="local", choices=["local", "docker", "cloud_run", "agent_runtime", "agent_engine", "gke"])
    p_dep.add_argument("--service-account", help="Dedicated IAM service account for Agent Runtime / Cloud Run")
    p_dep.add_argument("--dry-run", action="store_true", default=True, help="Generate deployment plan without mutating cloud infrastructure (default: True)")
    p_dep.add_argument("--execute", action="store_true", help="Disable dry-run and execute deployment")
    p_dep.add_argument("--approve-billable", action="store_true", help="Explicitly authorize billable cloud resource creation")
    p_dep.add_argument("--json", action="store_true", help="Emit JSON output")

    # 15. smoke-test
    p_smk = sub.add_parser("smoke-test", help="Run post-build or post-deployment smoke test")
    p_smk.add_argument("--project-dir", default=".", help="Target ADK project directory")
    p_smk.add_argument("--target", default="local", help="Deployment target name")
    p_smk.add_argument("--json", action="store_true", help="Emit JSON output")

    # 16. status
    p_sts = sub.add_parser("status", help="Inspect current 17-stage lifecycle checkpoint status for a project")
    p_sts.add_argument("--project-dir", default=".", help="Target ADK project directory")
    p_sts.add_argument("--json", action="store_true", help="Emit JSON output")

    # 17. integrations
    p_int = sub.add_parser("integrations", help="List and health-check registered ADK tools, providers, and templates")
    p_int.add_argument("--category", help="Filter integrations by category")
    p_int.add_argument("--json", action="store_true", help="Emit JSON output")

    # 18. skills
    p_skl = sub.add_parser("skills", help="Validate or package Agent Skills (SKILL.md frontmatter, layout, and path safety)")
    p_skl.add_argument("--skill-dir", default=".", help="Path to skill directory containing SKILL.md")
    p_skl.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    p_skl.add_argument("--package", action="store_true", help="Package the validated skill into a clean .skill archive")
    p_skl.add_argument("--output-dir", help="Optional output directory for .skill archive")
    p_skl.add_argument("--json", action="store_true", help="Emit JSON output")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    as_json = bool(getattr(args, "json", False))

    try:
        return _dispatch(args, as_json=as_json)
    except AdkBuilderError as exc:
        _emit({"status": "error", "error": exc.to_dict()}, as_json=as_json)
        return int(exc.exit_code)
    except Exception as exc:
        _emit(
            {
                "status": "error",
                "error": {
                    "error_code": "ADK_ERR_UNHANDLED",
                    "message": str(exc),
                },
            },
            as_json=as_json,
        )
        return int(ExitCode.GENERAL_ERROR)


def _dispatch(args: argparse.Namespace, *, as_json: bool) -> int:
    cmd = args.command

    if cmd == "doctor":
        cli_env = AdkCliAdapter.detect_environment()
        cfg = BuilderConfig.from_env_and_file()
        reg = IntegrationRegistry()
        payload = {
            "suite_version": __version__,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "cli_bridges": cli_env,
            "default_config": cfg.to_safe_dict(),
            "registered_providers": [p.value for p in PROVIDER_CATALOG.keys()],
            "registered_integrations_count": len(reg.list_all()),
            "registered_templates_count": len(list_templates()),
        }
        _emit(payload, as_json=as_json)
        return int(ExitCode.SUCCESS)

    if cmd == "audit":
        p_dir = Path(args.project_dir).resolve()
        val = ProjectValidator.validate_project(p_dir)
        sec = SecurityScanner.scan_project(p_dir)
        skl = SkillValidator.validate_skill_directory(p_dir) if (p_dir / "SKILL.md").exists() else None
        payload = {
            "project_dir": str(p_dir),
            "validation": val.to_dict(),
            "security": sec.to_dict(),
            "skill_validation": skl.to_dict() if skl else None,
        }
        _emit(payload, as_json=as_json)
        return int(ExitCode.SUCCESS if sec.passed else ExitCode.SECURITY_VIOLATION)

    if cmd == "init":
        spec = RequirementsEngine.from_natural_language(args.objective, project_name=args.name)
        out_path = Path(args.output)
        if not args.dry_run:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(yaml.safe_dump(spec.to_dict(), sort_keys=False), encoding="utf-8")
        _emit(
            {
                "status": "dry_run" if args.dry_run else "created",
                "output_file": str(out_path),
                "specification": spec.to_dict(),
            },
            as_json=as_json,
        )
        return int(ExitCode.SUCCESS)

    if cmd == "requirements":
        if args.spec:
            spec = RequirementsEngine.load_file(args.spec)
        elif args.from_text:
            spec = RequirementsEngine.from_natural_language(args.from_text, project_name=args.name)
        else:
            print("Provide either --spec or --from-text.", file=sys.stderr)
            return int(ExitCode.INVALID_ARGUMENTS)
        if args.output:
            out_p = Path(args.output)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            if out_p.suffix.lower() == ".json":
                out_p.write_text(spec.to_json(indent=2), encoding="utf-8")
            else:
                out_p.write_text(yaml.safe_dump(spec.to_dict(), sort_keys=False), encoding="utf-8")
        has_error = any(c.severity == "error" for c in spec.contradictions)
        _emit(spec.to_dict(), as_json=as_json)
        return int(ExitCode.REQUIREMENTS_ERROR if has_error else ExitCode.SUCCESS)

    if cmd == "plan":
        spec = RequirementsEngine.load_file(args.spec)
        plan = ArchitecturePlanner.plan(spec)
        if args.output:
            out_p = Path(args.output)
            out_p.parent.mkdir(parents=True, exist_ok=True)
            out_p.write_text(plan.to_json(indent=2), encoding="utf-8")
        _emit(plan.to_dict(), as_json=as_json)
        return int(ExitCode.SUCCESS)

    if cmd == "build":
        spec = RequirementsEngine.load_file(args.spec)
        if any(c.severity == "error" for c in spec.contradictions):
            _emit({"status": "blocked_by_contradictions", "contradictions": [c.to_dict() for c in spec.contradictions]}, as_json=as_json)
            return int(ExitCode.REQUIREMENTS_ERROR)

        plan = ArchitecturePlanner.plan(spec)
        out_dir = Path(args.output_dir).resolve()
        if args.dry_run:
            _emit({"status": "dry_run", "output_dir": str(out_dir), "plan": plan.to_dict()}, as_json=as_json)
            return int(ExitCode.SUCCESS)

        run_state = EngineeringRunState(
            run_id=f"run-{spec.project_name}",
            project_name=spec.project_name,
            project_dir=str(out_dir),
        )
        run_state.initialize_all_stages()
        run_state.mark_stage(LifecycleStage.STAGE_01_REQUIREMENT_INTAKE, StageStatus.PASSED)
        run_state.mark_stage(LifecycleStage.STAGE_02_CLARIFICATION_NORMALIZATION, StageStatus.PASSED)
        run_state.mark_stage(LifecycleStage.STAGE_03_FEASIBILITY_ANALYSIS, StageStatus.PASSED)
        run_state.mark_stage(LifecycleStage.STAGE_04_ARCHITECTURE_SELECTION, StageStatus.PASSED)
        run_state.mark_stage(LifecycleStage.STAGE_05_AGENT_WORKFLOW_PLANNING, StageStatus.PASSED)
        run_state.mark_stage(LifecycleStage.STAGE_06_TOOL_INTEGRATION_SELECTION, StageStatus.PASSED)

        files = ProjectGenerator.generate_project(spec, plan, out_dir, overwrite=True)
        run_state.mark_stage(LifecycleStage.STAGE_07_PROJECT_SCAFFOLDING, StageStatus.PASSED, artifacts=files)
        run_state.mark_stage(LifecycleStage.STAGE_08_AGENT_IMPLEMENTATION, StageStatus.PASSED, artifacts=["app/agent.py", "app/tools.py"])
        run_state.mark_stage(LifecycleStage.STAGE_09_CONFIGURATION_GENERATION, StageStatus.PASSED, artifacts=["pyproject.toml", "agents-cli-manifest.yaml"])

        val_res = ProjectValidator.validate_project(out_dir)
        sec_res = SecurityScanner.scan_project(out_dir)
        tst_res = TestRunner.run_tests(out_dir)
        eval_res = EvaluationEngine.evaluate_project(out_dir)

        if args.repair and (not val_res.valid or not sec_res.passed or not tst_res.passed or not eval_res.overall_passed):
            repair_rep = DiagnosticsAndRepairEngine.run_bounded_repair(out_dir)
            run_state.repair_history = [r.to_dict() for r in repair_rep.repair_history]
            run_state.mark_stage(
                LifecycleStage.STAGE_13_FAILURE_DIAGNOSIS_REMEDIATION,
                StageStatus.PASSED if repair_rep.final_healthy else StageStatus.FAILED,
            )
            val_res = ProjectValidator.validate_project(out_dir)
            sec_res = SecurityScanner.scan_project(out_dir)
            tst_res = TestRunner.run_tests(out_dir)
            eval_res = EvaluationEngine.evaluate_project(out_dir)
        else:
            run_state.mark_stage(LifecycleStage.STAGE_13_FAILURE_DIAGNOSIS_REMEDIATION, StageStatus.SKIPPED)

        run_state.mark_stage(
            LifecycleStage.STAGE_10_UNIT_INTEGRATION_TESTING,
            StageStatus.PASSED if tst_res.passed else StageStatus.FAILED,
            metrics={"passed": tst_res.passed_tests, "failed": tst_res.failed_tests},
        )
        run_state.mark_stage(
            LifecycleStage.STAGE_11_SECURITY_POLICY_VALIDATION,
            StageStatus.PASSED if sec_res.passed else StageStatus.FAILED,
        )
        run_state.mark_stage(
            LifecycleStage.STAGE_12_EVALUATION_ACCEPTANCE,
            StageStatus.PASSED if eval_res.overall_passed else StageStatus.FAILED,
            metrics=eval_res.aggregate_scores,
        )

        obs_manifest = ObservabilityManager.generate_observability_manifest(
            ObservabilityConfig(enabled_exporters=spec.observability_backends)
        )
        (out_dir / "observability.json").write_text(json.dumps(obs_manifest, indent=2), encoding="utf-8")
        run_state.mark_stage(LifecycleStage.STAGE_16_OBSERVABILITY_CONFIGURATION, StageStatus.PASSED, artifacts=["observability.json"])

        dep_plan = DeploymentManager.create_deployment_plan(out_dir, spec.deployment_target, dry_run=True)
        run_state.mark_stage(LifecycleStage.STAGE_14_PACKAGING_DEPLOYMENT_PLANNING, StageStatus.PASSED)
        smoke = DeploymentManager.run_smoke_test(out_dir, spec.deployment_target)
        run_state.mark_stage(
            LifecycleStage.STAGE_15_DEPLOYMENT_SMOKE_TESTING,
            StageStatus.PASSED if smoke.passed else StageStatus.FAILED,
        )
        run_state.mark_stage(LifecycleStage.STAGE_17_MAINTENANCE_REGRESSION, StageStatus.PASSED)
        run_state.save(out_dir / ".adk_builder_state/lifecycle_state.json")

        all_ok = val_res.valid and sec_res.passed and tst_res.passed and eval_res.overall_passed and smoke.passed
        _emit(
            {
                "status": "completed" if all_ok else "failed",
                "project_dir": str(out_dir),
                "created_files": files,
                "validation_valid": val_res.valid,
                "security_passed": sec_res.passed,
                "tests_passed": tst_res.passed,
                "evaluation_passed": eval_res.overall_passed,
                "smoke_test_passed": smoke.passed,
                "deployment_plan": dep_plan.to_dict(),
            },
            as_json=as_json,
        )
        return int(ExitCode.SUCCESS if all_ok else ExitCode.VALIDATION_FAILED)

    if cmd == "validate":
        p_dir = Path(args.project_dir).resolve()
        if args.repair:
            rep = DiagnosticsAndRepairEngine.run_bounded_repair(p_dir)
            val = ProjectValidator.validate_project(p_dir)
            sec = SecurityScanner.scan_project(p_dir)
            _emit(
                {
                    "repair_report": rep.to_dict(),
                    "validation": val.to_dict(),
                    "security": sec.to_dict(),
                },
                as_json=as_json,
            )
            return int(ExitCode.SUCCESS if (val.valid and sec.passed) else ExitCode.SELF_REPAIR_EXHAUSTED)

        val = ProjectValidator.validate_project(p_dir)
        sec = SecurityScanner.scan_project(p_dir)
        _emit({"validation": val.to_dict(), "security": sec.to_dict()}, as_json=as_json)
        if not sec.passed:
            return int(ExitCode.SECURITY_VIOLATION)
        return int(ExitCode.SUCCESS if val.valid else ExitCode.VALIDATION_FAILED)

    if cmd == "test":
        p_dir = Path(args.project_dir).resolve()
        res = TestRunner.run_tests(p_dir, test_subdir=args.subdir, timeout_seconds=args.timeout)
        _emit(res.to_dict(), as_json=as_json)
        return int(ExitCode.SUCCESS if res.passed else ExitCode.TEST_FAILED)

    if cmd == "eval":
        p_dir = Path(args.project_dir).resolve()
        eval_p = Path(args.evalset) if args.evalset else None
        cfg_p = Path(args.config) if args.config else None
        rep = EvaluationEngine.evaluate_project(p_dir, evalset_path=eval_p, config_path=cfg_p)
        if args.output:
            out_f = Path(args.output)
            out_f.parent.mkdir(parents=True, exist_ok=True)
            out_f.write_text(rep.to_json(indent=2), encoding="utf-8")
        _emit(rep.to_dict(), as_json=as_json)
        return int(ExitCode.SUCCESS if rep.overall_passed else ExitCode.EVALUATION_FAILED)

    if cmd == "quota":
        spec_p = Path(args.spec).resolve()
        models = [m.strip() for m in args.rotate_models.split(",") if m.strip()] or ["gemini-2.5-flash"]
        policy = QuotaBudgetPolicy(
            daily_message_limit=args.daily_limit,
            requests_per_minute_limit=args.rpm_limit,
            rotate_models=models,
        )
        ledger_p = Path(args.ledger).resolve() if args.ledger else (spec_p.parent / ".adk_quota_ledger.json")
        rep = QuotaBudgetManager.estimate_and_plan(
            spec_p,
            policy=policy,
            ledger_path=ledger_p,
            slice_size=args.slice_size,
        )
        _emit(rep.to_dict(), as_json=as_json)
        return int(ExitCode.SUCCESS)

    if cmd == "dashboard":
        in_p = Path(args.input).resolve()
        out_p = Path(args.output).resolve() if args.output else None
        eval_md_p = Path(args.evaluation_md).resolve() if args.evaluation_md else None
        written = DashboardRenderer.render_from_file(in_p, out_p, evaluation_md_path=eval_md_p)
        _emit({"status": "rendered", "input": str(in_p), "dashboard_html": str(written)}, as_json=as_json)
        return int(ExitCode.SUCCESS)

    if cmd == "report":
        p_dir = Path(args.project_dir).resolve()
        state_file = p_dir / ".adk_builder_state/lifecycle_state.json"
        lifecycle_data = (
            EngineeringRunState.load(state_file).to_dict() if state_file.exists() else {"status": "no_saved_state"}
        )
        val = ProjectValidator.validate_project(p_dir)
        sec = SecurityScanner.scan_project(p_dir)
        diags = [d.to_dict() for d in DiagnosticsAndRepairEngine.diagnose_project(p_dir)]
        payload = {
            "project_dir": str(p_dir),
            "lifecycle": lifecycle_data,
            "validation": val.to_dict(),
            "security": sec.to_dict(),
            "diagnostics": diags,
        }
        if args.output:
            Path(args.output).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        _emit(payload, as_json=as_json)
        return int(ExitCode.SUCCESS)

    if cmd == "package":
        p_dir = Path(args.project_dir).resolve()
        if args.dry_run:
            val = ProjectValidator.validate_project(p_dir)
            _emit({"status": "dry_run", "valid": val.valid, "project_dir": str(p_dir)}, as_json=as_json)
            return int(ExitCode.SUCCESS if val.valid else ExitCode.VALIDATION_FAILED)
        out_zip = Path(args.output).resolve() if args.output else None
        archive = DeploymentManager.package_project(p_dir, out_zip)
        _emit({"status": "packaged", "archive_path": str(archive)}, as_json=as_json)
        return int(ExitCode.SUCCESS)

    if cmd == "deploy":
        p_dir = Path(args.project_dir).resolve()
        is_dry = not bool(args.execute)
        plan = DeploymentManager.create_deployment_plan(
            p_dir,
            args.target,
            dry_run=is_dry,
            approve_billable=bool(args.approve_billable),
            service_account=args.service_account,
        )
        _emit(plan.to_dict(), as_json=as_json)
        return int(ExitCode.SUCCESS)

    if cmd == "smoke-test":
        p_dir = Path(args.project_dir).resolve()
        smk = DeploymentManager.run_smoke_test(p_dir, args.target)
        _emit(smk.to_dict(), as_json=as_json)
        return int(ExitCode.SUCCESS if smk.passed else ExitCode.TEST_FAILED)

    if cmd == "status":
        p_dir = Path(args.project_dir).resolve()
        state_file = p_dir / ".adk_builder_state/lifecycle_state.json"
        if not state_file.exists():
            _emit({"project_dir": str(p_dir), "status": "uninitialized"}, as_json=as_json)
            return int(ExitCode.SUCCESS)
        state = EngineeringRunState.load(state_file)
        _emit(state.to_dict(), as_json=as_json)
        return int(ExitCode.SUCCESS)

    if cmd == "integrations":
        reg = IntegrationRegistry()
        specs = reg.list_all(category=args.category)
        payload = {
            "integrations": [s.to_dict() for s in specs],
            "health": [reg.check_health(s.id) for s in specs],
            "providers": {k.value: v.to_dict() for k, v in PROVIDER_CATALOG.items()},
            "templates": [t.to_dict() for t in list_templates()],
        }
        _emit(payload, as_json=as_json)
        return int(ExitCode.SUCCESS)

    if cmd == "skills":
        s_dir = Path(args.skill_dir).resolve()
        if args.package:
            out_d = Path(args.output_dir).resolve() if args.output_dir else None
            pkg_rep = SkillValidator.package_skill_archive(s_dir, output_dir=out_d)
            _emit(pkg_rep.to_dict(), as_json=as_json)
            return int(ExitCode.SUCCESS)
        rep = SkillValidator.validate_skill_directory(s_dir, strict=bool(args.strict))
        _emit(rep.to_dict(), as_json=as_json)
        return int(ExitCode.SUCCESS if rep.valid else ExitCode.VALIDATION_FAILED)

    return int(ExitCode.INVALID_ARGUMENTS)


if __name__ == "__main__":
    sys.exit(main())
