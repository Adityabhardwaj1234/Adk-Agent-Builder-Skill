# Architecture and multi-agent orchestration (ADK 2.x, Python)

All snippets below were instantiated against google-adk 2.12.0 and the import paths re-verified against the installed package. Use `MODEL = "gemini-flash-latest"` or the exact id that `adk create` wrote into `agent.py`.

Companion references: `data-memory-skills.md` (state, databases, memory, ADK Skills, MCP, guardrails), `evaluation.md` (test specs and scoring), `pitfalls.md` (verified gotchas), `deployment.md` (shipping the agent).

## Contents
1. Decision table
2. Single LlmAgent
3. Coordinator + sub-agents (LLM-driven delegation)
4. AgentTool (agent as a tool)
5. Sequential / Parallel / Loop workflow agents
6. ADK 2.0 graph workflows (`Workflow`, routes, `JoinNode`)
7. Collaboration modes (`chat`, `task`, `single_turn`)
8. A2A (remote agents)
9. Passing data between agents
10. Orchestration quality checklist

## 1. Decision table

| Situation | Use |
|---|---|
| One job, a few tools | One `Agent` (LlmAgent) |
| Several distinct skills, user free-form, routing by intent | Coordinator `Agent` with `sub_agents=[...]` (transfer) |
| Specialist must be *consulted* and the parent keeps control and answers | `AgentTool(agent=specialist)` |
| Fixed order: A then B then C | `SequentialAgent` (or graph `Workflow` if you need branching) |
| Independent tasks that can run at once, then merge | `ParallelAgent` -> merge agent, or graph fan-out + `JoinNode` |
| Draft -> critique -> revise until good | `LoopAgent` with `exit_loop` tool and `max_iterations` |
| Deterministic business process with branching, code steps, human approval | ADK 2.0 `Workflow` graph |
| Remote/other-team/other-language agent | A2A (`RemoteA2aAgent`, `to_a2a`) |

Rule of thumb: put **control flow in code** (workflow agents/graphs) and **reasoning in LLM agents**. If you find yourself writing "first do X, then Y, then Z" in a long instruction, that is a sequential or graph workflow.

## 2. Single LlmAgent

```python
from google.adk.agents import Agent
root_agent = Agent(
    name="root_agent",                       # unique, identifier-like
    model="gemini-flash-latest",
    description="One line describing what this agent does (used by parents for routing).",
    instruction="""Role...
Steps...
Use tool `x` when ... Never ...
Reply format: ...""",
    tools=[my_function],
    # output_key="result",                   # saves final text into state["result"]
    # output_schema=MyPydanticModel,         # structured JSON output
    # input_schema=MyInput,                  # agent expects a JSON message matching this
    # generate_content_config=types.GenerateContentConfig(temperature=0.2),
    # planner=BuiltInPlanner(thinking_config=...),
)
```
`include_contents='none'` makes a sub-agent stateless (it sees only its own instruction + state), which keeps context small for pipeline stages.

## 3. Coordinator with sub-agents

```python
billing = Agent(name="billing", model=MODEL,
    description="Handles invoices, refunds and payment failures.",   # specific + mutually exclusive
    instruction="Resolve billing problems using the billing tools.", tools=[lookup_invoice])
support = Agent(name="support", model=MODEL,
    description="Handles technical problems: login, errors, outages.", instruction="...", tools=[search_kb])
root_agent = Agent(name="help_desk", model=MODEL,
    description="Front door of the help desk.",
    instruction="Greet briefly, then route: billing questions -> billing, technical -> support. "
                "Answer small talk yourself.",
    sub_agents=[billing, support])
```
The LLM calls `transfer_to_agent(agent_name=...)`; responsibility moves to the sub-agent and **later user turns go to it** until it transfers back (sub-agents can transfer to parent/peers unless `disallow_transfer_to_parent` / `disallow_transfer_to_peers` is set). Test routing with `agents_involved` expectations.

## 4. AgentTool (parent keeps control)

```python
from google.adk.tools import AgentTool
root_agent = Agent(name="writer", model=MODEL, instruction="Use `researcher` for facts, then write the answer.",
                   tools=[AgentTool(agent=researcher)])
```
Use for built-in tools that cannot share an agent (Google Search, code execution): wrap the single-tool agent in `AgentTool`.

## 5. Workflow agents (prebuilt)

```python
from google.adk.agents import SequentialAgent, ParallelAgent, LoopAgent
from google.adk.tools import exit_loop

a = Agent(name="researcher_a", model=MODEL, instruction="Research topic A.", output_key="a_result")
b = Agent(name="researcher_b", model=MODEL, instruction="Research topic B.", output_key="b_result")
fan_out = ParallelAgent(name="fan_out", sub_agents=[a, b])                 # branches run concurrently, no shared history
synth = Agent(name="synth", model=MODEL, instruction="Combine {a_result} and {b_result}.", output_key="final")
pipeline = SequentialAgent(name="pipeline", sub_agents=[fan_out, synth])

writer = Agent(name="writer", model=MODEL, instruction="Write a draft. Improve it using {critique?}.", output_key="draft")
critic = Agent(name="critic", model=MODEL, instruction="Critique {draft}. If it is good call exit_loop.",
               tools=[exit_loop], output_key="critique")
refine = LoopAgent(name="refine", sub_agents=[writer, critic], max_iterations=3)   # ALWAYS bound the loop
```
- Agents in a pipeline communicate through **session state**: producer sets `output_key`, consumer reads `{key}` in its instruction.
- Parallel branches must write **different** `output_key`s (race otherwise).
- A workflow agent can be a sub-agent of a coordinator, e.g. `root_agent = Agent(..., sub_agents=[pipeline, refine])`.

## 6. ADK 2.0 graph workflows

Nodes can be agents, tools, plain Python functions, human-input steps or nested workflows. A function node receives `node_input` (previous node's output) and returns a value or an `Event`.

```python
from google.adk import Agent, Event, Workflow
from google.adk.workflow import JoinNode

classifier = Agent(name="classifier", model=MODEL,
    instruction='Classify the message as exactly one word: BUG, SUPPORT or LOGISTICS.')

def router(node_input: str):
    return Event(route=node_input.strip().upper())        # route string(s) select outgoing edges

def handle_bug():      return Event(message="Handling bug...")
def handle_support():  return Event(message="Handling support...")

root_agent = Workflow(
    name="routing_workflow",
    edges=[
        ("START", classifier, router),
        (router, {"BUG": handle_bug, "SUPPORT": handle_support}),   # dict = conditional edges
    ],
)
```
Fan-out/fan-in:
```python
join = JoinNode(name="join")
edges=[("START", task_a, join), ("START", task_b, join), ("START", task_c, join), (join, final_task)]
```
Notes (from ADK 2.0 docs and tests):
- `Event(message=...)` is what the user sees; `Event(output=...)` is data for the next node; `Event(route=...)` (string or list) picks branches. Graph messages arrive with `role=user` but `author=<workflow name>` - `testing.py` handles this.
- A cycle (back-edge) is **not** bounded automatically; make the exit condition certain or use `LoopAgent`/dynamic workflow.
- Use `input_schema`/`output_schema` (Pydantic) on nodes to constrain data between steps.
- Human-in-the-loop and dynamic (code-driven) workflows exist; see the ADK docs pages "Human input" and "Dynamic workflows" when needed.
- Do **not** wrap tool code in a broad `except Exception:` - ADK 2 retries/pauses on exceptions; never catch `BaseException`.
- Some third-party integrations are not yet compatible with graph workflows.
- Python function nodes make a graph testable **without any LLM call**, which is why graph workflows are good for deterministic business logic.
- Upgrading from ADK 1.x: ADK 2.0 changed the Event schema (`node_info`, `output`) - custom session stores with rigid columns need migration.

## 7. Collaboration modes (coordinator + typed sub-agents)

```python
from pydantic import BaseModel
weather = Agent(name="weather_checker", model=MODEL, mode="single_turn", tools=[get_weather])   # no user chat, auto-returns, can run in parallel
flights = Agent(name="flight_booker", model=MODEL, mode="task",                                  # may ask clarifying questions, auto-returns via finish_task
                input_schema=FlightInput, output_schema=FlightResult, tools=[search_flights, book_flight])
root = Agent(name="travel_planner", model=MODEL, sub_agents=[weather, flights])                  # delegation tools named after each sub-agent
```
Never set `mode` on the root agent. `task` agents must be leaf agents. In graph workflows `task` mode is currently disabled in Python 2.0.0 - use `single_turn` there.

## 8. A2A (needs `pip install "google-adk[a2a]"`)

Expose: `from google.adk.a2a.utils.agent_to_a2a import to_a2a; a2a_app = to_a2a(root_agent, port=8001)` then `uvicorn module:a2a_app`.
Consume: `from google.adk.agents.remote_a2a_agent import RemoteA2aAgent, AGENT_CARD_WELL_KNOWN_PATH`
`RemoteA2aAgent(name="prime_agent", description="...", agent_card=f"http://localhost:8001/a2a/prime_agent{AGENT_CARD_WELL_KNOWN_PATH}")`, then place it in `sub_agents`. Use A2A only for genuinely separate services; local sub-agents are faster and simpler. Reusing the same remote-agent instance under several parents needs `.clone()`.

## 9. Passing data between agents

| Mechanism | When |
|---|---|
| `output_key` + `{key}` in the next instruction | Pipelines (default choice) |
| `tool_context.state["k"] = v` inside a tool | Tools producing structured data |
| Graph node return value -> next `node_input` | Graph workflows |
| `input_schema`/`output_schema` | Typed contracts between steps |
| `temp:` prefix in state | Scratch values valid for one invocation only |
| `user:` / `app:` prefix | Persist across sessions for a user / the whole app |

## 10. Orchestration quality checklist

- Every sub-agent has a one-sentence, non-overlapping `description`.
- Coordinator instruction names each specialist and the trigger for it; it says what to do when no specialist fits.
- No agent instance appears under two parents; names are unique across the tree.
- Loops are bounded; parallel branches write distinct keys; every `{key}` used is produced earlier (or marked `{key?}`).
- Specialists have the **fewest tools** needed (less confusion, cheaper, safer).
- Cross-cutting rules live in one place (a `GlobalInstructionPlugin` on the `App`, or callbacks) instead of being pasted into every agent.
- Each routing path has a `multi_agent` test with `agents_involved` / `routes_include`, plus one negative test (`agents_excluded`).
