Done. The skill is now a complete, self-contained ADK agent-building suite — built, tested, and packaged entirely inside adk-agent-builder/. Nothing outside the skill folder was touched (the skills-creator repo's Apex files have only their pre-existing changes), and nothing is committed — say the word if you want a commit.
What's there now
adk-agent-builder/
├── SKILL.md                     # rewritten: workflow Steps 0-8, verified ADK 2.12 facts, 170 lines
├── scripts/
│   ├── create_agent.py          # scaffold: venv + pip + adk create (flags only, no menus) + verify + JSON report
│   ├── testing.py               # test harness: introspect -> api_server -> spec runs -> score -> classify
│   ├── dashboard.py             # results.json -> standalone HTML report (inline CSS, no CDN)
│   ├── deploy_agent.py          # adk deploy wrapper: preflight + secret audit + --dry-run + report
│   ├── quick_validate.py        # frontmatter/naming validator + doc-integrity (catches stale doc paths)
│   └── package_skill.py         # builds a clean, verified .skill archive (never ships .env/*.db/tests)
├── references/
│   ├── architecture.md          # (moved) agent types, orchestration, graph workflows, A2A
│   ├── data-memory-skills.md    # state, sessions/DBs, memory, ADK Skills, MCP, guardrails
│   ├── evaluation.md            # spec schema, assertions, rubric, failure -> fix table
│   ├── pitfalls.md              # verified gotchas (quota-as-HTTP-500, .env override, Windows, races)
│   └── deployment.md            # Cloud Run / Agent Engine / Docker / GKE + secret handling
├── assets/                      # tested copy-and-adapt templates
│   ├── multi_agent_agent.py     # coordinator + specialists, status-dict tools
│   ├── graph_agent.py           # routing graph + fan-out/JoinNode graph
│   ├── sqlite_tools.py          # parameterised, validated SQLite tools
│   └── spec_example.json        # full 8-test spec for the template
├── tests/test_offline.py        # 38 tests, zero API calls
└── dist/adk-agent-builder.skill # packaged archive (16 files, 71 KB, integrity-verified)
How to Use it
python scripts/create_agent.py my_app --workspace ./ws --api-key "$GOOGLE_API_KEY"
python scripts/testing.py --workspace ./ws --app my_app --init-spec
# fill the spec, then:
python scripts/testing.py --workspace ./ws --app my_app --spec ws/adk_runs/spec.json --min-interval 13 --retry-infra 2
python scripts/dashboard.py --results ws/adk_runs/<timestamp>/results.json
python scripts/deploy_agent.py ./ws/my_app --mode cloud_run --project P --region us-central1 --dry-run
Ship it by copying dist/adk-agent-builder.skill wherever you install skills from — that archive is exactly what the installer will unpack.
