"""Incident reports given to TracePilot. They describe symptoms only, never causes."""

ORDERS_API = """Two reports came in for the orders_api service:
1. Users say GET /orders/9/total sometimes returns 500.
2. A security reviewer suspects users can see other users' orders.

Test credentials for the sandbox: 'token-alice' (user 1) and 'token-bob' (user 2), sent as 'Authorization: Bearer <token>'."""
