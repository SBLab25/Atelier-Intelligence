"""
Read and workflow services shared by the /api/v1 adapter, the CLI and the dashboard (Spec 12, OD-125).

Each function takes what it needs (settings, repository, workflow) as arguments, so the HTTP layer, the CLI and
tests choose the implementations. Errors are the domain errors (RepositoryError, WorkflowRuntimeError, ...);
adapters translate them.
"""
