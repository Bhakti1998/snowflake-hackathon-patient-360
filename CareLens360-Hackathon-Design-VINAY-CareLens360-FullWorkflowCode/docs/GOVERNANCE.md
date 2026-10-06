# Full-MVP governance and access

Owner: Spurthi. Synthetic-only does not mean unrestricted permissions.

## Required controls from PDF section 13

- Approved database with separate raw, curated, semantic and application schemas.
  `RAW`, `CURATED`, `SEMANTIC`, `APP` are proposed physical names, not PDF-mandated names.
- `CARE_ADMIN`: approved project setup and implementation privileges, not an
  invitation to grant account-wide administration.
- `CARE_DATA_ENGINEER`: pipeline access within approved project boundaries.
- `CARE_ANALYST`: governed curated views and approved semantic metrics.
- `CARE_REVIEWER`: authorized Member 360/evidence access.
- `CARE_DEMO_USER`: app-only user experience. Determine required application,
  warehouse, agent, model, and service privileges from the actual execution
  model; do not assume all objects execute with the same owner's rights.
- Visible synthetic-data/demo-score disclaimer in the application.
- Pipeline run IDs/status/error details and provenance retained for debugging.
- Member/plan row-level filtering, data classification columns, audit logging,
  and pipeline audit records are mandatory, not deferred work.
- No real PHI, secrets, access tokens, private keys, or signed download URLs in
  repository files, model context, or judging artifacts.

Use a pre-authorized administrative role for role/grant creation. Verify current
role, account, warehouse, feature/region availability, database, schemas, and
object ownership before DDL. Ask for approval before changing grants, replacing
objects, uploading/overwriting files, or incurring material model/warehouse cost.

## Permission verification

1. Test positive and negative permissions for all five roles: setup for admin,
   pipeline for engineer, governed views for analyst, authorized Member 360 for
   reviewer, and app-only behavior for demo user. Record approved privileges.
2. Test the Streamlit app, member lookup, approved agent invocation, and citation
   display as `CARE_DEMO_USER`.
3. Test direct raw table/file access as `CARE_DEMO_USER`; it should be denied
   under the app-only intent.
4. If the chosen app execution mode needs extra privileges, document the exact
   least-privilege mechanism and test it. Do not solve a grant error with broad
   raw access or assume application access proves role isolation.
5. Create at least two entitlement/member-plan test groups. Test authorized and
   unauthorized members/plans through tables/views, Analyst, Search, agent, UI,
   source-file access and cached responses. Changing UI selection must not
   bypass a policy or retain another member's evidence.
6. Verify classification metadata and audit records for successful/denied access
   and pipeline success/failure. Retention and sensitive-field redaction require
   explicit approval; logs must not become a secondary PHI/secret store.

Search filters provide relevance scoping, **not row-level authorization**.
Inspect the actual Search service execution/owner-rights behavior and whether
source policies protect retrieval consumers. If they do not, implement an
approved isolation boundary (for example entitlement-scoped services and grants
or an authenticated access layer) and negative-test it. Do not infer that a
table row policy automatically secures an index or a client-supplied filter.

## Policy and audit implementation

- Define the approved entitlement mapping for principals/roles to members/plans.
  Enforce deny-by-default for absent/invalid mappings, except documented admin
  privileges. Shared guidelines are separated from member-specific notes.
- Apply row-access policies or an equivalent approved server-side mechanism to
  every exposing surface; record owner-rights and direct-API implications.
- Retain classification labels on governed data and documents; define handling
  rules for exports, evidence bundles and app source links.
- Persist pipeline file/run/version, operation, status, timing and error details.
  Record application/query access outcomes without storing private reasoning.
- Implement approved audit capture/retention and verify records from actual
  executions; a proposed audit task is not evidence of logging.

All controls must pass before declaring MVP completion. Full-MVP scope still
does not mean production readiness or clinical validation.

## Evidence sanitation

Capture configuration, synthetic lineage, safe query/run IDs, and redacted
outputs. Inspect artifacts before sharing. Do not publish private attachments,
repository content, or fixtures to GitHub, a stage, or an external service merely
to make skills reusable; distribution requires explicit approval.
