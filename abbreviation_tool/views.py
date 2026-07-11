from django.conf import settings
from django.contrib.auth.decorators import login_required, permission_required
from django.db import models
from datetime import timedelta
import json
import logging
from pathlib import Path

from django.core.exceptions import ValidationError
from django.contrib import messages
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import DictionarySearchForm, DocumentUploadForm, QuickProcessForm
from .models import AbbreviationEntry, AbbreviationProfile, DocumentProcessingSession
from .storage import cleanup_expired, expire_session, save_original
from .services.analysis import analyse_session
from .services.preview import build_preview
from .services.review import bulk_decide, decide, history_action
from .services.generation import generate_session, glossary_rows
from .storage import PROCESSED_NAME, session_directory


logger = logging.getLogger(__name__)


def _feature_enabled():
    return settings.DOCX_ABBREVIATION_TOOL_ENABLED


def _require_feature():
    if not _feature_enabled():
        raise Http404("SD Checker is disabled.")


@login_required
@permission_required("abbreviation_tool.access_abbreviation_tool", raise_exception=True)
def landing(request):
    _require_feature()
    cleanup_expired()
    if not request.user.has_perm("abbreviation_tool.process_document"):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    form = QuickProcessForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        active_sessions = DocumentProcessingSession.objects.filter(user=request.user, deleted_at__isnull=True, expires_at__gt=timezone.now()).count()
        if active_sessions >= settings.DOCX_ABBREVIATION_MAX_ACTIVE_SESSIONS:
            return render(request, "abbreviation_tool/landing.html", {"form": form, "error": "Please wait for an existing document session to expire or cancel it."}, status=429)
        document = form.cleaned_data["docx_file"]
        profile = AbbreviationProfile.objects.filter(name="General", active=True).first() or AbbreviationProfile.objects.filter(active=True).first()
        session = DocumentProcessingSession.objects.create(
            user=request.user,
            original_filename=Path(document.name).name[:255],
            operation_type=form.cleaned_data["operation_type"],
            profile=profile,
            replacement_policy=DocumentProcessingSession.Policy.ALL,
            processing_options={"include_tables": True, "include_headers_footers": True, "include_footnotes_endnotes": True, "glossary_mode": "none"},
            file_size=document.size,
            unsupported_element_count=len(form.inspection.unsupported_elements),
            expires_at=timezone.now() + timedelta(minutes=settings.DOCX_ABBREVIATION_SESSION_TTL_MINUTES),
        )
        try:
            save_original(session, document)
            analyse_session(session, policy=session.replacement_policy, include_tables=True)
            session.suggestions.filter(ambiguity_status="unambiguous").update(review_status="accepted")
            session.suggestions.filter(ambiguity_status="ambiguous").update(review_status="rejected")
            session.accepted_count = session.suggestions.filter(review_status="accepted").count()
            session.rejected_count = session.suggestions.filter(review_status="rejected").count()
            session.save(update_fields=("accepted_count", "rejected_count"))
            generate_session(session.id, request.user)
            path = session_directory(session.id) / PROCESSED_NAME
            filename = f"processed-{Path(session.original_filename).stem}.docx"
            response = FileResponse(path.open("rb"), as_attachment=True, filename=filename, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            response["Cache-Control"] = "no-store, private"
            response["X-Content-Type-Options"] = "nosniff"
            response._resource_closers.append(lambda: expire_session(session))
            return response
        except ValidationError as exc:
            expire_session(session, status=DocumentProcessingSession.Status.FAILED)
            return render(request, "abbreviation_tool/landing.html", {"form": form, "error": exc.messages[0]}, status=400)
        except Exception:
            logger.exception("Quick DOCX processing failed", extra={"processing_session_id": str(session.id), "user_id": request.user.id})
            expire_session(session, status=DocumentProcessingSession.Status.FAILED)
            return render(request, "abbreviation_tool/landing.html", {"form": form, "error": "The document could not be processed. Temporary files were deleted."}, status=400)
    return render(request, "abbreviation_tool/landing.html", {
        "form": form,
        "entry_count": AbbreviationEntry.objects.filter(status=AbbreviationEntry.Status.ACTIVE).count(),
    })


@login_required
@permission_required("abbreviation_tool.process_document", raise_exception=True)
def text_convert(request):
    _require_feature()
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed."}, status=405)
    data = _payload(request)
    text = str(data.get("text", ""))
    operation = data.get("operation")
    if operation not in {DocumentProcessingSession.Operation.ABBREVIATE, DocumentProcessingSession.Operation.DEABBREVIATE}:
        return JsonResponse({"error": "Choose abbreviate or deabbreviate."}, status=400)
    if not text.strip() or len(text) > 50_000:
        return JsonResponse({"error": "Enter between 1 and 50,000 characters."}, status=400)
    from .services.matching import POLICY_ALL, candidates_for, find_matches
    from .services.ooxml import CharacterLocation, TextContainer
    profile = AbbreviationProfile.objects.filter(name="General", active=True).first()
    container = TextContainer("text", "text:p0", "paragraph", text, [CharacterLocation(0, index, b"") for index in range(len(text))])
    matches = find_matches(container, candidates_for(profile, operation), operation, POLICY_ALL)
    if operation == DocumentProcessingSession.Operation.DEABBREVIATE:
        matches = [match for match in matches if match.ambiguity == "unambiguous"]
    output = text
    for match in sorted(matches, key=lambda item: item.start, reverse=True):
        output = output[:match.start] + match.proposed + output[match.end:]
    return JsonResponse({"result": output, "replacement_count": len(matches)})


@login_required
@permission_required("abbreviation_tool.search_dictionary", raise_exception=True)
def dictionary(request):
    _require_feature()
    form = DictionarySearchForm(request.GET)
    entries = AbbreviationEntry.objects.select_related("category").prefetch_related("profiles")
    if form.is_valid():
        query = form.cleaned_data.get("q")
        if query:
            entries = entries.filter(models.Q(abbreviation__icontains=query) | models.Q(full_form__icontains=query))
        if form.cleaned_data.get("service"):
            entries = entries.filter(service__iexact=form.cleaned_data["service"])
        if form.cleaned_data.get("status"):
            entries = entries.filter(status=form.cleaned_data["status"])
        if form.cleaned_data.get("ambiguous") is not None:
            entries = entries.filter(is_ambiguous=form.cleaned_data["ambiguous"])
    return render(request, "abbreviation_tool/dictionary.html", {"form": form, "entries": entries[:250]})


@login_required
@permission_required("abbreviation_tool.process_document", raise_exception=True)
def upload(request):
    _require_feature()
    active_sessions = DocumentProcessingSession.objects.filter(user=request.user, deleted_at__isnull=True, expires_at__gt=timezone.now()).count()
    if request.method == "POST" and active_sessions >= settings.DOCX_ABBREVIATION_MAX_ACTIVE_SESSIONS:
        return render(request, "abbreviation_tool/upload.html", {"form": DocumentUploadForm(), "limit_error": "Finish or cancel an existing document session before starting another."}, status=429)
    form = DocumentUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        document = form.cleaned_data["pdf_file"]
        session = DocumentProcessingSession.objects.create(
            user=request.user,
            original_filename=Path(document.name).name[:255],
            operation_type=form.cleaned_data["operation_type"],
            profile=form.cleaned_data["profile"],
            replacement_policy=form.cleaned_data["replacement_policy"],
            processing_options={
                "include_tables": form.cleaned_data["include_tables"],
                "include_headers_footers": form.cleaned_data["include_headers_footers"],
                "include_footnotes_endnotes": form.cleaned_data["include_footnotes_endnotes"],
                "case_sensitive": form.cleaned_data["case_sensitive"],
                "high_confidence_only": form.cleaned_data["high_confidence_only"],
                "glossary_mode": form.cleaned_data["glossary_mode"] or "none",
                "glossary_bookmark": form.cleaned_data["glossary_bookmark"],
            },
            file_size=document.size,
            unsupported_element_count=len(form.inspection.unsupported_elements),
            expires_at=timezone.now() + timedelta(minutes=settings.DOCX_ABBREVIATION_SESSION_TTL_MINUTES),
        )
        try:
            save_original(session, document)
        except Exception:
            session.delete()
            raise
        return redirect("abbreviation_tool:session", session_id=session.id)
    return render(request, "abbreviation_tool/upload.html", {"form": form})


@login_required
@permission_required("abbreviation_tool.process_document", raise_exception=True)
def session_detail(request, session_id):
    _require_feature()
    session = get_object_or_404(DocumentProcessingSession, id=session_id, user=request.user, deleted_at__isnull=True)
    if session.expires_at <= timezone.now():
        expire_session(session)
        raise Http404("This processing session has expired.")
    return render(request, "abbreviation_tool/session.html", {"processing_session": session})


@login_required
@permission_required("abbreviation_tool.process_document", raise_exception=True)
def cancel(request, session_id):
    _require_feature()
    if request.method != "POST":
        raise Http404
    session = get_object_or_404(DocumentProcessingSession, id=session_id, user=request.user, deleted_at__isnull=True)
    expire_session(session)
    return redirect("abbreviation_tool:landing")


@login_required
@permission_required("abbreviation_tool.process_document", raise_exception=True)
def analyse(request, session_id):
    _require_feature()
    if request.method != "POST":
        raise Http404
    session = get_object_or_404(DocumentProcessingSession, id=session_id, user=request.user, deleted_at__isnull=True)
    if session.expires_at <= timezone.now():
        expire_session(session)
        raise Http404("This processing session has expired.")
    try:
        analyse_session(session, policy=session.replacement_policy, include_tables=session.processing_options.get("include_tables", True))
        return redirect("abbreviation_tool:review", session_id=session.id)
    except ValidationError as exc:
        expire_session(session, status=DocumentProcessingSession.Status.FAILED)
        messages.error(request, exc.messages[0])
        return redirect("abbreviation_tool:landing")
    except Exception:
        logger.exception("DOCX analysis failed", extra={"processing_session_id": str(session.id), "user_id": request.user.id})
        expire_session(session, status=DocumentProcessingSession.Status.FAILED)
        messages.error(request, "Document analysis failed and its temporary files were deleted.")
        return redirect("abbreviation_tool:landing")


def _owned_review_session(user, session_id):
    session = get_object_or_404(DocumentProcessingSession.objects.prefetch_related("suggestions__abbreviation_entry__category"), id=session_id, user=user, deleted_at__isnull=True)
    if session.expires_at <= timezone.now():
        expire_session(session)
        raise Http404("This processing session has expired.")
    if session.status != DocumentProcessingSession.Status.REVIEW:
        raise Http404("This session is not ready for review.")
    return session


@login_required
@permission_required("abbreviation_tool.process_document", raise_exception=True)
def review(request, session_id):
    _require_feature()
    session = _owned_review_session(request.user, session_id)
    suggestions = session.suggestions.select_related("abbreviation_entry__category", "selected_meaning").order_by("container_identifier", "start_offset")
    ambiguity_options = {}
    for suggestion in suggestions.filter(ambiguity_status="ambiguous"):
        ambiguity_options[str(suggestion.id)] = list(AbbreviationEntry.objects.filter(
            normalized_abbreviation=suggestion.abbreviation_entry.normalized_abbreviation,
            status=AbbreviationEntry.Status.ACTIVE,
        ).values("id", "full_form"))
    return render(request, "abbreviation_tool/review.html", {
        "processing_session": session,
        "suggestions": suggestions,
        "preview": build_preview(session),
        "ambiguity_options": ambiguity_options,
        "categories": suggestions.exclude(abbreviation_entry__category__isnull=True).values_list("abbreviation_entry__category__name", flat=True).distinct(),
        "glossary": glossary_rows(session),
    })


def _payload(request):
    try:
        return json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise ValidationError("Invalid JSON request.") from exc


@login_required
@permission_required("abbreviation_tool.process_document", raise_exception=True)
def suggestion_api(request, session_id, suggestion_id):
    _require_feature()
    if request.method not in {"PATCH", "POST"}:
        return JsonResponse({"error": "Method not allowed."}, status=405)
    session = _owned_review_session(request.user, session_id)
    data = _payload(request)
    try:
        suggestion = decide(session_id, request.user, suggestion_id, data.get("action"), data.get("replacement", ""), data.get("selected_meaning_id"))
        return JsonResponse({"ok": True, "status": suggestion.review_status, "replacement": suggestion.user_modified_text or suggestion.proposed_text})
    except (ValidationError, AbbreviationEntry.DoesNotExist) as exc:
        message = exc.messages[0] if isinstance(exc, ValidationError) else "The selected meaning is invalid."
        return JsonResponse({"error": message}, status=400)


@login_required
@permission_required("abbreviation_tool.process_document", raise_exception=True)
def bulk_review_api(request, session_id):
    _require_feature()
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed."}, status=405)
    _owned_review_session(request.user, session_id)
    data = _payload(request)
    try:
        bulk_decide(session_id, request.user, data.get("action"), bool(data.get("high_confidence")), data.get("suggestion_ids"))
        return JsonResponse({"ok": True})
    except ValidationError as exc:
        return JsonResponse({"error": exc.messages[0]}, status=400)


@login_required
@permission_required("abbreviation_tool.process_document", raise_exception=True)
def history_api(request, session_id):
    _require_feature()
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed."}, status=405)
    _owned_review_session(request.user, session_id)
    try:
        history_action(session_id, request.user, _payload(request).get("direction"))
        return JsonResponse({"ok": True})
    except ValidationError as exc:
        return JsonResponse({"error": exc.messages[0]}, status=400)


@login_required
@permission_required("abbreviation_tool.process_document", raise_exception=True)
def generate(request, session_id):
    _require_feature()
    if request.method != "POST":
        raise Http404
    session = _owned_review_session(request.user, session_id)
    try:
        generate_session(session_id, request.user)
        return redirect("abbreviation_tool:summary", session_id=session_id)
    except ValidationError as exc:
        session.refresh_from_db()
        if session.status == DocumentProcessingSession.Status.FAILED:
            expire_session(session, status=DocumentProcessingSession.Status.FAILED)
            messages.error(request, f"{exc.messages[0]} Temporary files were deleted.")
            return redirect("abbreviation_tool:landing")
        messages.error(request, exc.messages[0])
        return redirect("abbreviation_tool:review", session_id=session_id)
    except Exception:
        logger.exception("DOCX generation failed", extra={"processing_session_id": str(session_id), "user_id": request.user.id})
        session = get_object_or_404(DocumentProcessingSession, id=session_id, user=request.user)
        expire_session(session, status=DocumentProcessingSession.Status.FAILED)
        messages.error(request, "DOCX generation failed and its temporary files were deleted.")
        return redirect("abbreviation_tool:landing")


@login_required
@permission_required("abbreviation_tool.process_document", raise_exception=True)
def summary(request, session_id):
    _require_feature()
    session = get_object_or_404(DocumentProcessingSession, id=session_id, user=request.user, status=DocumentProcessingSession.Status.COMPLETE, deleted_at__isnull=True)
    return render(request, "abbreviation_tool/summary.html", {"processing_session": session})


@login_required
@permission_required("abbreviation_tool.process_document", raise_exception=True)
def download(request, session_id):
    _require_feature()
    session = get_object_or_404(DocumentProcessingSession, id=session_id, user=request.user, status=DocumentProcessingSession.Status.COMPLETE, deleted_at__isnull=True)
    path = session_directory(session.id) / PROCESSED_NAME
    if not path.is_file():
        raise Http404("The generated document is no longer available.")
    filename = f"processed-{Path(session.original_filename).stem}.docx"
    response = FileResponse(path.open("rb"), as_attachment=True, filename=filename, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    response["Cache-Control"] = "no-store, private"
    response["X-Content-Type-Options"] = "nosniff"
    response._resource_closers.append(lambda: expire_session(session))
    return response


@login_required
@permission_required("abbreviation_tool.process_document", raise_exception=True)
def glossary_download(request, session_id):
    _require_feature()
    session = get_object_or_404(DocumentProcessingSession, id=session_id, user=request.user, deleted_at__isnull=True)
    if session.processing_options.get("glossary_mode") not in {"preview", "separate"}:
        raise Http404("A separate glossary was not selected for this session.")
    rows = glossary_rows(session)
    if not rows:
        return JsonResponse({"error": "No glossary entries are available."}, status=400)
    from django.http import HttpResponse
    content = "Abbreviation\tFull Form\n" + "\n".join(f"{abbreviation}\t{full_form}" for abbreviation, full_form in rows)
    response = HttpResponse(content, content_type="text/tab-separated-values; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="abbreviation-glossary.tsv"'
    response["Cache-Control"] = "no-store, private"
    response["X-Content-Type-Options"] = "nosniff"
    return response
