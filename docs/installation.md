# Installation & Compatibility Guide (`docs/installation.md`)

## 1. Runtime Prerequisites

- **Python**: Python `3.11`, `3.12`, or `3.13` (ADK v2.12.0 also supports up to Python 3.15).
- **Core Dependencies**: `PyYAML>=6.0` and `pydantic>=1.10.4,<3.0.0` (compatible with both Pydantic v1 and Pydantic v2).

## 2. Installing the Core Toolkit

```bash
pip install -e .
```

Or run directly from source without global installation:

```bash
PYTHONPATH=src python3 -m adk_agent_builder.cli doctor --json
```

## 3. Optional Extras

Keep the core installation lightweight and install provider or protocol extras only when needed:

```bash
# Install Google ADK runtime
pip install -e ".[adk]"

# Install Google Agents CLI integration
pip install -e ".[agents-cli]"

# Install OpenAI, Anthropic, or LiteLLM adapters
pip install -e ".[openai,anthropic,litellm]"

# Install MCP and A2A protocol extras
pip install -e ".[mcp,a2a]"

# Install development & test extras
pip install -e ".[dev]"
```
