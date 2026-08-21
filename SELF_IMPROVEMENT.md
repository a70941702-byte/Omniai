# Self Improvement

The self-improvement flow is:

`Observe -> Analyze -> Plan/Proposal -> Patch -> Static validation -> Sandbox/Tests -> Evaluation -> Owner Approval -> Apply -> Checkpoint -> Monitor -> Rollback`

The agent reads production source but writes experiments to the independent Git workspace. Approved code patches are validated and applied only through `ApprovalSystem`; test failure restores the pre-change backup.
