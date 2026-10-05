# Prepare the sample index

The grant in [`DEPLOY.md`](DEPLOY.md) is scoped to one index, so the index has to
exist first. Nothing in this package creates it. The platform's index script
does, and it changes shared Search data, so a person approves each step that
writes.

The sample set is ten fictional policy passages in
[`policy-guidance.json`](../../hosted-agents/knowledge-sample/policy-guidance.json)
(version `sample-v1`). They contain no customer, personal, or health
information. Your own documents can't be added with this package.

## Before you start

- Get approval for the sample set's version and digest, the index name
  (`lab-sample-policy-guidance` unless you choose another), and the temporary
  operator roles.
- Take a read-only inventory of the Search service first: its indexes, who owns
  each, and how each would be removed. Stop if anything is unexpected. See
  [Shared Search cautions](../../docs/knowledge-retrieval.md#shared-search-cautions).
- Run from the private network. The service has public network access and local
  (key) authentication off, so there's no other way in, and none should be
  added.

## Roles for the person loading the index

The person who loads the index needs **Search Service Contributor** and
**Search Index Data Contributor** on the Search service, only while loading.
Assign them to that person, never to the agent, and remove them afterward. Don't
use admin keys. The agent only ever gets **Search Index Data Reader** on the one
index, from the module.

## Steps

From `hosted-agents`:

```powershell
python knowledge_index.py plan
python knowledge_index.py load --confirm
python knowledge_index.py verify
```

1. `plan` is offline. It prints the version and digest to approve.
2. `load --confirm` creates the dedicated index, uploads the passages, and ends
   with `verify`. Confirm it reports the approved version and digest.
3. Remove the temporary operator roles.

Then continue with [`DEPLOY.md`](DEPLOY.md). The design, roles, and checks are
in [Knowledge retrieval](../../docs/knowledge-retrieval.md#sample-documents-and-the-index-script).
