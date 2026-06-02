AI Agent Review Prototype
=========================

This workspace is a small Python prototype for an AI code review tool.

How the pieces map
------------------

1. main.py is the CLI entrypoint.
2. review_engine.py contains the review rules.
3. review_types.py defines the report shape.

What the MVP checks
-------------------

- Hallucinated imports or missing dependencies
- Dead code in the current file
- Unnecessary abstraction layers
- Duplicate logic
- Suspicious AI-generated patterns
- Missing tests for the reviewed file

Run it
------

Review a file:

```bash
python main.py path\to\file.py
```

Run the demo sample:

```bash
python main.py --demo
```

Teaching note
-------------

The current architecture is intentionally small:

- input: a Python file path or the built-in demo source
- analysis: AST-based review rules
- output: a score plus actionable findings

That gives us a clean first MVP before adding GitHub PR integration.
"# CodeSentinel" 
