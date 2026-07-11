# DOCX Abbreviation Manager

## Integration architecture

This module is integrated into the existing Django 6 application as `abbreviation_tool`. It uses the existing Django users, sessions, CSRF protection, permissions, admin site, SQLite database, server-rendered templates, dashboard navigation, fixed footer, error messages, and Django test runner. It introduces no parallel authentication, frontend framework, database, or deployment stack.

The workflow is: authenticated upload → strict OOXML validation → isolated UUID session → deterministic analysis → controlled review → direct OOXML generation → owner-only one-time download → cleanup.

## Configuration

Required feature flag:

```text
DOCX_ABBREVIATION_TOOL_ENABLED=true
```

Optional limits:

```text
DOCX_ABBREVIATION_MAX_UPLOAD_MB=25
DOCX_ABBREVIATION_SESSION_TTL_MINUTES=30
DOCX_ABBREVIATION_TEMP_ROOT=/secure/private/path
DOCX_ABBREVIATION_MAX_UNCOMPRESSED_MB=250
DOCX_ABBREVIATION_MAX_ZIP_RATIO=100
DOCX_ABBREVIATION_MAX_ZIP_MEMBERS=5000
DOCX_ABBREVIATION_MAX_ACTIVE_SESSIONS=5
DOCX_ABBREVIATION_MAX_SUGGESTIONS=5000
DOCX_ABBREVIATION_ANALYSIS_TIMEOUT_SECONDS=60
```

Run `python manage.py cleanup_abbreviation_sessions` at least every 15 minutes in production. The tool also cleans expired sessions when its landing page is opened.

## Route map

- `/tools/docx-abbreviations/` — landing
- `/tools/docx-abbreviations/upload/` — upload and options
- `/tools/docx-abbreviations/dictionary/` — dictionary search
- `/tools/docx-abbreviations/sessions/<uuid>/` — session status
- `/tools/docx-abbreviations/sessions/<uuid>/analyse/` — analysis
- `/tools/docx-abbreviations/sessions/<uuid>/review/` — preview and review
- `/tools/docx-abbreviations/sessions/<uuid>/generate/` — generation
- `/tools/docx-abbreviations/sessions/<uuid>/summary/` — summary
- `/tools/docx-abbreviations/sessions/<uuid>/download/` — one-time output
- `/tools/docx-abbreviations/sessions/<uuid>/glossary/` — optional TSV glossary
- `/admin/abbreviation_tool/` — administration

Review JSON endpoints use authenticated Django sessions and CSRF:

- `PATCH .../suggestions/<uuid>/`
- `POST .../suggestions/bulk/`
- `POST .../history/`

## Data model

The module contains categories, profiles, dictionary entries, approved variants, temporary processing sessions, temporary suggestions, and permanent dictionary audit metadata. Document bodies, preview HTML, and files are not stored in the database.

JSSDM Section 16 Annex 16A records are migrated into the controlled dictionary. The legacy `jssdm` table remains intact for rollback and the existing checker.

## Permissions

`DOCX Abbreviation Users` receives access, processing, and dictionary-search permissions. `DOCX Abbreviation Administrators` additionally receives dictionary import/export/management, profile management, and audit access. Assign users through Django admin.

## Cleanup

Cancellation, logout, expiry, failed analysis, failed generation, and completed downloads remove session files and suggestions. Session directories are mode `0700`; files are mode `0600`. Paths are server-derived from UUIDs and never returned to clients.
