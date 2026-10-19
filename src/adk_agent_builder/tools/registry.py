"""Extensible Integration & Tool Registry for Google ADK."""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from pydantic import Field

from adk_agent_builder.models.base import CompatModel


class IntegrationStatus(str, Enum):
    IMPLEMENTED = "implemented"
    ADAPTER_SUPPORTED = "supported_through_adapter"
    OPTIONAL = "optional"
    EXPERIMENTAL = "experimental"
    PLANNED = "planned"
    UNSUPPORTED = "unsupported"


class ToolIntegrationSpec(CompatModel):
    """Typed specification for a tool or external service integration in ADK."""

    id: str
    name: str
    category: str
    status: IntegrationStatus
    adk_import_path: str
    adk_class_or_symbol: str
    extra_dependency: Optional[str] = None
    requires_credentials: bool = False
    required_env_vars: List[str] = Field(default_factory=list)
    supports_streaming: bool = False
    supports_human_confirmation: bool = True
    default_timeout_seconds: float = 15.0
    input_schema: Dict[str, str] = Field(default_factory=dict)
    output_schema: Dict[str, str] = Field(default_factory=dict)
    limitations: List[str] = Field(default_factory=list)
    official_docs_url: str = "https://adk.dev/tools/built-in-tools/"


BUILT_IN_INTEGRATIONS: Dict[str, ToolIntegrationSpec] = {
    "custom_function_tool": ToolIntegrationSpec(
        id="custom_function_tool",
        name="Custom Python FunctionTool",
        category="core_tools",
        status=IntegrationStatus.IMPLEMENTED,
        adk_import_path="google.adk.tools",
        adk_class_or_symbol="FunctionTool",
        requires_credentials=False,
        supports_streaming=True,
        supports_human_confirmation=True,
        input_schema={"query": "str"},
        output_schema={"status": "str", "result": "Any"},
        limitations=["Function parameters must have explicit Python type annotations and docstrings."],
        official_docs_url="https://adk.dev/tools/function-tools/",
    ),
    "long_running_generator_tool": ToolIntegrationSpec(
        id="long_running_generator_tool",
        name="Streaming / Long-Running Generator FunctionTool",
        category="core_tools",
        status=IntegrationStatus.IMPLEMENTED,
        adk_import_path="google.adk.tools",
        adk_class_or_symbol="LongRunningFunctionTool",
        requires_credentials=False,
        supports_streaming=True,
        supports_human_confirmation=True,
        input_schema={"task_id": "str"},
        output_schema={"progress": "float", "status": "str"},
        limitations=["Non-live generator FunctionTools run via FunctionNode in ADK v2.12.0+."],
        official_docs_url="https://adk.dev/tools/function-tools/",
    ),
    "google_search": ToolIntegrationSpec(
        id="google_search",
        name="Google Search Grounding Tool",
        category="grounding",
        status=IntegrationStatus.ADAPTER_SUPPORTED,
        adk_import_path="google.adk.tools",
        adk_class_or_symbol="google_search",
        requires_credentials=True,
        required_env_vars=["GEMINI_API_KEY"],
        supports_streaming=False,
        supports_human_confirmation=False,
        input_schema={"query": "str"},
        output_schema={"grounded_chunks": "List[Dict]"},
        limitations=["Supported on Gemini 2.0+ / Gemini 3+ models; sub-agent use requires ADK v2.12.0+ when mixed with custom tools."],
        official_docs_url="https://adk.dev/grounding/google-search-grounding/",
    ),
    "code_execution": ToolIntegrationSpec(
        id="code_execution",
        name="Isolated Code Execution Tool",
        category="execution",
        status=IntegrationStatus.ADAPTER_SUPPORTED,
        adk_import_path="google.adk.code_executors",
        adk_class_or_symbol="BuiltInCodeExecutor",
        requires_credentials=True,
        required_env_vars=["GEMINI_API_KEY"],
        supports_streaming=False,
        supports_human_confirmation=True,
        input_schema={"code": "str"},
        output_schema={"stdout": "str", "stderr": "str"},
        limitations=["Never use host-unsafe local execution in untrusted environments; prefer container/pod isolation or Vertex Code Interpreter."],
        official_docs_url="https://adk.dev/tools/built-in-tools/",
    ),
    "openapi_toolset": ToolIntegrationSpec(
        id="openapi_toolset",
        name="OpenAPI 3.x Spec Toolset",
        category="api_integration",
        status=IntegrationStatus.ADAPTER_SUPPORTED,
        adk_import_path="google.adk.tools.openapi_tool",
        adk_class_or_symbol="OpenAPIToolset",
        requires_credentials=False,
        supports_streaming=False,
        supports_human_confirmation=True,
        input_schema={"spec_str": "str", "spec_str_type": "str"},
        output_schema={"tools": "List[RestApiTool]"},
        limitations=["Requires valid OpenAPI 3.0/3.1 JSON or YAML specification and explicit auth scheme mapping."],
        official_docs_url="https://adk.dev/tools/openapi-tools/",
    ),
    "mcp_toolset": ToolIntegrationSpec(
        id="mcp_toolset",
        name="Model Context Protocol (MCP) Toolset",
        category="protocol",
        status=IntegrationStatus.ADAPTER_SUPPORTED,
        adk_import_path="google.adk.tools.mcp_tool",
        adk_class_or_symbol="MCPToolset",
        extra_dependency="mcp>=1.1.0,<3.0.0",
        requires_credentials=False,
        required_env_vars=["MCP_SERVER_URL"],
        supports_streaming=True,
        supports_human_confirmation=True,
        input_schema={"connection_params": "StdioServerParameters | SseServerParams"},
        output_schema={"tools": "List[MCPTool]"},
        limitations=["Supports MCP SDK 1.x and opt-in modern protocol 2.x (ADK v2.11.0+); stdio servers require explicit opt-in."],
        official_docs_url="https://adk.dev/tools/mcp-tools/",
    ),
    "bigquery_toolset": ToolIntegrationSpec(
        id="bigquery_toolset",
        name="Google Cloud BigQuery Toolset",
        category="database",
        status=IntegrationStatus.OPTIONAL,
        adk_import_path="google.adk.tools.bigquery",
        adk_class_or_symbol="BigQueryToolset",
        extra_dependency="google-cloud-bigquery>=3.20.0",
        requires_credentials=True,
        required_env_vars=["GOOGLE_CLOUD_PROJECT"],
        supports_streaming=False,
        supports_human_confirmation=True,
        input_schema={"project_id": "str", "dataset_id": "str", "sql_query": "str"},
        output_schema={"rows": "List[Dict]"},
        limitations=["Protected write mode rejects non-SELECT statements without an anonymous session dataset destination (ADK v2.10.0+)."],
        official_docs_url="https://adk.dev/tools/built-in-tools/",
    ),
    "mongodb_toolset": ToolIntegrationSpec(
        id="mongodb_toolset",
        name="MongoDB Vector & Hybrid Search Toolset",
        category="database",
        status=IntegrationStatus.OPTIONAL,
        adk_import_path="google.adk.tools.mongodb",
        adk_class_or_symbol="MongoDBToolset",
        extra_dependency="pymongo>=4.6.0",
        requires_credentials=True,
        required_env_vars=["MONGODB_URI"],
        supports_streaming=False,
        supports_human_confirmation=True,
        input_schema={"query_vector": "List[float]", "filter": "Dict"},
        output_schema={"documents": "List[Dict]"},
        limitations=["Introduced in ADK v2.10.0; requires Atlas Vector Search index for hybrid retrieval."],
        official_docs_url="https://github.com/google/adk-python/releases/tag/v2.10.0",
    ),
    "vertex_rag_retrieval": ToolIntegrationSpec(
        id="vertex_rag_retrieval",
        name="Vertex AI RAG Retrieval Tool",
        category="retrieval",
        status=IntegrationStatus.OPTIONAL,
        adk_import_path="google.adk.tools.retrieval",
        adk_class_or_symbol="VertexAiRagRetrieval",
        extra_dependency="google-cloud-aiplatform>=2.2.0",
        requires_credentials=True,
        required_env_vars=["GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "VERTEX_RAG_CORPUS"],
        supports_streaming=False,
        supports_human_confirmation=False,
        input_schema={"query": "str"},
        output_schema={"contexts": "List[str]"},
        limitations=["Migrated away from vertexai.preview to google-cloud-aiplatform v2.2 in ADK v2.12.0."],
        official_docs_url="https://adk.dev/tools/built-in-tools/",
    ),
    "gcs_artifact_tools": ToolIntegrationSpec(
        id="gcs_artifact_tools",
        name="File & Artifact Context Tools (load_artifact / GCS)",
        category="artifacts",
        status=IntegrationStatus.IMPLEMENTED,
        adk_import_path="google.adk.tools",
        adk_class_or_symbol="load_artifacts",
        requires_credentials=False,
        supports_streaming=False,
        supports_human_confirmation=False,
        input_schema={"artifact_names": "List[str]"},
        output_schema={"artifacts": "List[Part]"},
        limitations=["GCS local file tools strictly confine paths to configured local_file_root (ADK v2.9.0+)."],
        official_docs_url="https://adk.dev/artifacts/",
    ),
    "remote_a2a_agent": ToolIntegrationSpec(
        id="remote_a2a_agent",
        name="Remote Agent2Agent (A2A) Client & Server",
        category="multi_agent",
        status=IntegrationStatus.ADAPTER_SUPPORTED,
        adk_import_path="google.adk.agents.remote_a2a_agent",
        adk_class_or_symbol="RemoteA2aAgent",
        extra_dependency="a2a-sdk>=0.2.0",
        requires_credentials=False,
        required_env_vars=["A2A_REMOTE_AGENT_URL"],
        supports_streaming=True,
        supports_human_confirmation=True,
        input_schema={"agent_card_url": "str", "message": "str"},
        output_schema={"events": "List[Event]"},
        limitations=["Non-loopback agent card URLs require HTTPS (ADK v2.9.0+); set use_legacy=False to enable A2A extension."],
        official_docs_url="https://adk.dev/a2a/",
    ),
    "model_consult_tool": ToolIntegrationSpec(
        id="model_consult_tool",
        name="Mid-Task Model Consultation Tool",
        category="reasoning",
        status=IntegrationStatus.ADAPTER_SUPPORTED,
        adk_import_path="google.adk.tools",
        adk_class_or_symbol="ModelConsultTool",
        requires_credentials=True,
        required_env_vars=["GEMINI_API_KEY"],
        supports_streaming=False,
        supports_human_confirmation=False,
        input_schema={"question": "str", "context": "str"},
        output_schema={"advisor_response": "str"},
        limitations=["Added in ADK v2.11.0; advisor models are invoked without tools and capped by per-turn and per-session budgets."],
        official_docs_url="https://github.com/google/adk-python/releases/tag/v2.11.0",
    ),
}


class IntegrationRegistry:
    """Extensible registry for discovering, validating, and health-checking ADK integrations."""

    def __init__(self) -> None:
        self._items: Dict[str, ToolIntegrationSpec] = dict(BUILT_IN_INTEGRATIONS)
        self._health_checks: Dict[str, Callable[[], Dict[str, Any]]] = {}

    def register(
        self,
        spec: ToolIntegrationSpec,
        health_check: Optional[Callable[[], Dict[str, Any]]] = None,
    ) -> None:
        """Register a custom or third-party integration specification."""
        self._items[spec.id] = spec
        if health_check:
            self._health_checks[spec.id] = health_check

    def get(self, integration_id: str) -> Optional[ToolIntegrationSpec]:
        return self._items.get(integration_id)

    def list_all(self, *, category: Optional[str] = None) -> List[ToolIntegrationSpec]:
        specs = list(self._items.values())
        if category:
            specs = [s for s in specs if s.category == category]
        return sorted(specs, key=lambda x: x.id)

    def check_health(
        self,
        integration_id: str,
        env: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Run a non-destructive readiness and credential check for an integration."""
        import os

        environment = env if env is not None else dict(os.environ)
        spec = self.get(integration_id)
        if not spec:
            return {"id": integration_id, "healthy": False, "error": "Unknown integration ID"}

        if integration_id in self._health_checks:
            return self._health_checks[integration_id]()

        missing_env = [v for v in spec.required_env_vars if not environment.get(v)]
        if spec.id == "google_search" or spec.id == "code_execution" or spec.id == "model_consult_tool":
            if environment.get("GEMINI_API_KEY") or environment.get("GOOGLE_API_KEY"):
                missing_env = []

        return {
            "id": spec.id,
            "name": spec.name,
            "status": spec.status.value,
            "healthy": len(missing_env) == 0 or not spec.requires_credentials,
            "requires_credentials": spec.requires_credentials,
            "missing_env_vars": missing_env,
            "default_timeout_seconds": spec.default_timeout_seconds,
            "supports_human_confirmation": spec.supports_human_confirmation,
        }
