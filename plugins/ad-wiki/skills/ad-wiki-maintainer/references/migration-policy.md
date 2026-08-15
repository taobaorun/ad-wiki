# Migration Policy

Treat Plugin version, AD-Wiki Profile version, and OKF version as separate identities.

Before migrating:

1. Read `profile_version` from `ad-wiki.yaml` and `okf_version` from root `wiki/index.md`.
2. Identify every affected file and the compatibility behavior for old readers.
3. Record the migration write set, validation, rollback point, and reviewer.
4. Require explicit approval because profile and directory migrations are high risk.

During migration:

- Use deterministic transformations for mechanical changes.
- Preserve unknown frontmatter fields.
- Never rewrite registered Raw files.
- Do not silently convert missing `status` to `draft`; OKF defines missing status as stable, so changing it is semantic.
- Preserve deprecated Concepts when existing links depend on them.
- Keep runtime Receipts outside the Bundle.

After migration:

1. Rebuild all indexes.
2. Add a newest-first ISO-date log entry.
3. Run full validation and Raw guard.
4. Compare semantic content and lifecycle state with the pre-migration boundary.
5. Stop before commit, push, or publication unless separately authorized.

Plugin upgrades never trigger migration automatically. Each knowledge repository owner chooses when to migrate.
