# Security checklist and limitations

Implemented controls include authentication, granular permissions, CSRF, ownership filtering, UUID sessions, feature gating, upload and expanded-size limits, ZIP-entry limits, compression-ratio limits, path-traversal rejection, macro/encryption/executable rejection, XML declaration checks, external-relationship rejection, secure filesystem modes, processing limits, no-store downloads, MIME-sniffing protection, one-time cleanup, logout cleanup, expiry cleanup, and content-free technical logging.

Production must additionally configure HTTPS, secure cookies, HSTS after HTTPS validation, a production secret key, `DEBUG=False`, `ALLOWED_HOSTS`, reverse-proxy upload limits, and a cleanup scheduler. A local antivirus scanner is recommended but is not currently integrated. SQLite is suitable for the current private deployment but PostgreSQL is recommended for significant concurrency.

Known limitations:

- SmartArt, WordArt, equations, floating text boxes, embedded Office objects, tracked-change edge cases, and unsupported custom XML remain unchanged and are not editable.
- Preview is structural and does not reproduce Word pagination.
- Replacement text uses the first matched character’s style across mixed-format runs.
- External OOXML relationships are rejected rather than fetched.
- Processing is synchronous and bounded by configured limits.
- Glossary insertion supports the document end or a body-level bookmark.
- Local antivirus scanning and distributed background workers are not configured.
