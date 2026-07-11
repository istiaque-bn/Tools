import os
import shutil
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .models import DocumentProcessingSession


ORIGINAL_NAME = "original.docx"
PROCESSED_NAME = "processed.docx"


def session_root():
    root = Path(settings.DOCX_ABBREVIATION_TEMP_ROOT).resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    return root


def session_directory(session_id, create=False):
    root = session_root()
    directory = (root / str(session_id)).resolve()
    if directory.parent != root:
        raise ValueError("Invalid processing session identifier.")
    if create:
        directory.mkdir(mode=0o700, exist_ok=False)
    return directory


def save_original(session, upload):
    directory = session_directory(session.id, create=True)
    destination = directory / ORIGINAL_NAME
    try:
        with destination.open("xb") as output:
            os.chmod(destination, 0o600)
            for chunk in upload.chunks():
                output.write(chunk)
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return destination


def delete_session_files(session):
    directory = session_directory(session.id)
    if directory.exists():
        shutil.rmtree(directory)


def expire_session(session, status=DocumentProcessingSession.Status.DELETED):
    delete_session_files(session)
    session.suggestions.all().delete()
    session.status = status
    session.deleted_at = timezone.now()
    session.save(update_fields=("status", "deleted_at"))


def cleanup_expired(now=None):
    now = now or timezone.now()
    sessions = DocumentProcessingSession.objects.filter(expires_at__lte=now, deleted_at__isnull=True)
    count = 0
    for session in sessions.iterator():
        expire_session(session)
        count += 1
    cutoff = (now - timedelta(minutes=settings.DOCX_ABBREVIATION_SESSION_TTL_MINUTES)).timestamp()
    active_ids = {str(value) for value in DocumentProcessingSession.objects.filter(deleted_at__isnull=True, expires_at__gt=now).values_list("id", flat=True)}
    for directory in session_root().iterdir():
        if directory.is_dir() and directory.name not in active_ids and directory.stat().st_mtime <= cutoff:
            shutil.rmtree(directory)
            count += 1
    return count


def cleanup_user_sessions(user):
    sessions = DocumentProcessingSession.objects.filter(user=user, deleted_at__isnull=True)
    for session in sessions.iterator():
        expire_session(session)
