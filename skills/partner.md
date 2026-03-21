---
name: procrastination-partner
capabilities: [bash, web_fetch]
---

# Objective
Identify upcoming uOttawa deadlines and prepare a local project skeleton for each.

# Workflow
1. Fetch deadlines: GET http://bridge:3000/deadlines
   - Header: x-bridge-token: <value of BRIDGE_SECRET env var>
2. For each deadline, read the description via web_fetch on the task link.
3. Create a folder in /workspace/output/[CourseID]-[TaskTitle].
4. Write a README.md inside each folder summarizing the task and due date.

# Technical Boundaries
- /workspace/uOttawa is read-only. You may read files there but cannot modify them.
- All output must go to /workspace/output only.
- bash is limited to: ls, cat, grep, mkdir, touch
- Do not attempt HTTP methods other than GET.