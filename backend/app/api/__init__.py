"""FastAPI routes and the SSE stream (spec 3).

**The privacy seam runs through this package.** Everything served from here
comes out of `case:{seed}`, which holds public information only. No route
reads a mind, no route takes a graph name or an agent id (project rules,
rule 6), and no ground-truth label from `backend/app/referee/` is ever put in
a response body (rule 2). `test_api.py` walks every route's output and holds
it to that.
"""
