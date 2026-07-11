# Rollback procedure

1. Set `DOCX_ABBREVIATION_TOOL_ENABLED=false`. Navigation is hidden and routes return disabled responses without deleting dictionary data.
2. Run `python manage.py cleanup_abbreviation_sessions` to remove temporary files.
3. Back up the database.
4. If code rollback is required, remove the `abbreviation_tool` URL include, app registration, dashboard card, settings, templates, static assets, and package dependency.
5. Reverse migrations only after confirming no dictionary changes need preservation: `python manage.py migrate abbreviation_tool zero`.

The legacy `jssdm.Abbreviation` table remains available and is not deleted by feature disablement. Reversing migrations deletes the new module’s dictionary and audit records, so database backup is mandatory.
