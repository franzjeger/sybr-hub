# External integration acceptance gate

Local tests exercise provider contracts and simulated failures. They do not
establish that writes work against a real Autotask or myITprocess account.
No live provider objects were created during this remediation.

For each integration, record the tested provider/API version, test organisation,
minimum granted permissions, field mappings and a named test operator. Use a
designated test tenant and synthetic records, not a first customer in production.

Verify a successful read, pagination, an invalid mapping, missing permissions,
required custom fields, rate limiting and timeout behavior. For writes, also
verify the exact persisted fields, two simultaneous submissions, reconnect after
an ambiguous POST and the provider's own duplicate/idempotency behavior.
Keep anonymised responses as fixtures and record cleanup of test objects.

External finding writes now reserve a durable operation before the provider
request. Pending and unknown outcomes block automatic retry, including after
restart. They have no automatic expiry because the object may already exist.

```bash
python scripts/reconcile_finding.py
```

Stop the hub and inspect the provider. Record an existing object with
`--operation ID --external-id PROVIDER_ID --service-stopped`. Only if the provider
confirms that no object was created, release the reservation using
`--operation ID --confirmed-no-remote-object --service-stopped`. Both commands
change local bookkeeping only. Never infer absence from a timeout alone.

For AI, API mode uses the configured model and bounded conversations. The user
must acknowledge external processing; messages, customer context and read-tool
results reach Anthropic. Structured secret fields are removed and output is
bounded, but arbitrary free text can still be sensitive. Write tools require a
single-use approval tied to the actual caller, tool and parameters. Approval
results appear in the operator UI and are not automatically sent to the model.
The legacy CLI mode is disabled because its unrestricted shell bypassed this
control and wrote an API token into a shared temporary helper file.
