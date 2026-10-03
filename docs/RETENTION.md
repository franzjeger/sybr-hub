# Customer retirement and data retention

The customer action retires a registration; it does not claim to erase every
copy of its data. The registration moves to encrypted `retired_customers/`,
active tenant keyring secrets are removed, and the ID remains reserved. Audits,
reports, certificates and DB history remain until a separate purge. Backups
include retired registrations so their identity remains recoverable.

Choose retention periods for operational evidence, shared security logs,
backups and exported reports before deployment. This release does not choose
an organisation's retention period or silently delete its backups.

To purge a retired customer's primary local records:

```bash
python scripts/purge_customer.py CUSTOMER_ID
```

Review the printed file paths and relational row counts. Stop the hub and its
collectors. Then apply that exact customer purge:

```bash
python scripts/purge_customer.py CUSTOMER_ID --apply \
  --confirm CUSTOMER_ID --service-stopped
```

The command deletes the retired configuration, its customer audit directories,
custom customer certificate and DB rows explicitly linked by `customer_id` or
`local_customer_id`. It refuses a directory shared by another active customer.
Before DB commit, a failure restores staged paths. An interrupted cleanup after
commit may leave `.sybr-purge-*` siblings; remove those after checking the outcome.

Complete these separate checks before representing the purge as total erasure:

- Rotate/expire backups and snapshots containing the customer, including copies
  outside this host. A later restore can reintroduce deleted records.
- Apply the separate retention policy to shared activity logs, exported CSV/PDF
  files, downloaded archives, support bundles and externally retained reports.
- Review shared SSH keys, provider cache mappings, old customer names and custom
  paths not represented by the current registration. Shared objects are not
  automatically destroyed based on a name match.
- Revoke provider-side app registrations, certificates, accounts and other
  external credentials using the provider's own workflow when appropriate.
  Local retirement or purge makes no external API changes.

Old format-2 backup ZIPs expose the SQLite payload even when they contain a
password-wrapped master key. Treat them as sensitive plaintext data. Format 3
encrypts every payload member with authenticated AES-GCM; filenames, manifest
metadata and the separately wrapped master-key member remain visible. Without
an export password, restoring requires the existing master key. With a password,
that password protects a portable copy of the key as well as access to payloads.
