# Administrator guide

Use Django admin under **DOCX Abbreviation Manager** to manage entries, categories, profiles, approved variants, and audit records.

Dictionary entries normalize Unicode-aware case and whitespace. Duplicate normalized abbreviation/full-form pairs are rejected. Mark every entry in a multi-meaning abbreviation group as ambiguous, designate preferred meanings only where policy permits, and use profile inclusion/exclusion for deterministic service context.

Dictionary create, update, and delete operations through admin generate metadata-only audit records. Do not place sensitive document text in dictionary notes.

Assign standard users to `DOCX Abbreviation Users`. Assign trusted dictionary administrators to `DOCX Abbreviation Administrators`. Superusers retain Django’s normal full access.

Schedule:

```bash
python manage.py cleanup_abbreviation_sessions
```

Monitor counts and failures without logging filenames, extracted text, preview content, or replacement context.
