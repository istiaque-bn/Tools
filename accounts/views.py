from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db import models
from django.shortcuts import get_object_or_404, redirect, render

from abbreviation_tool.models import AbbreviationAuditLog, AbbreviationEntry, DocumentProcessingSession, Feedback

from .decorators import admin_required
from .forms import AdminUserCreationForm, UserAdministrationForm
from .models import UserProfile
from .utils import is_admin_user


User = get_user_model()


def _admin_count():
    return User.objects.filter(models.Q(is_staff=True) | models.Q(is_superuser=True) | models.Q(profile__role=UserProfile.Role.ADMIN)).distinct().count()


@admin_required
def panel_dashboard(request):
    users = User.objects.select_related("profile")
    context = {
        "total_users": users.count(),
        "normal_users": users.filter(is_staff=False, is_superuser=False, profile__role=UserProfile.Role.USER).count(),
        "admin_users": _admin_count(),
        "total_abbreviations": AbbreviationEntry.objects.count(),
        "open_feedback": Feedback.objects.filter(resolved=False).count(),
        "active_sessions": DocumentProcessingSession.objects.filter(deleted_at__isnull=True).count(),
        "recent_users": users.order_by("-date_joined")[:6],
        "recent_feedback": Feedback.objects.select_related("user").order_by("-created_at")[:5],
    }
    return render(request, "admin_panel/dashboard.html", context)


@admin_required
def user_list(request):
    create_form = AdminUserCreationForm(request.POST or None) if request.method == "POST" and "create_user" in request.POST else AdminUserCreationForm()
    if request.method == "POST" and "create_user" in request.POST and create_form.is_valid():
        created_user = create_form.save()
        messages.success(request, f"User {created_user.username} was created successfully.")
        return redirect("admin_panel:user_list")
    if request.method == "POST" and "create_user" in request.POST and create_form.errors:
        messages.error(request, "The user was not created. Correct the highlighted fields and submit again.")
    query = " ".join(request.GET.get("q", "").split())[:200]
    role = request.GET.get("role", "")
    status = request.GET.get("status", "")
    users = User.objects.select_related("profile").order_by("username")
    if query:
        users = users.filter(models.Q(username__icontains=query) | models.Q(email__icontains=query) | models.Q(first_name__icontains=query) | models.Q(last_name__icontains=query))
    if role == UserProfile.Role.ADMIN:
        users = users.filter(models.Q(is_staff=True) | models.Q(is_superuser=True) | models.Q(profile__role=role)).distinct()
    elif role == UserProfile.Role.USER:
        users = users.filter(is_staff=False, is_superuser=False, profile__role=role)
    if status == "active":
        users = users.filter(is_active=True)
    elif status == "inactive":
        users = users.filter(is_active=False)
    return render(request, "admin_panel/user_list.html", {"users": users[:500], "query": query, "selected_role": role, "selected_status": status, "create_form": create_form, "show_create_form": request.method == "POST" and create_form.errors})


@admin_required
def user_detail(request, user_id):
    managed_user = get_object_or_404(User.objects.select_related("profile"), pk=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=managed_user, defaults={"role": UserProfile.Role.ADMIN if managed_user.is_staff or managed_user.is_superuser else UserProfile.Role.USER})
    initial_role = UserProfile.Role.ADMIN if is_admin_user(managed_user) else UserProfile.Role.USER
    form = UserAdministrationForm(request.POST or None, initial={"role": initial_role, "is_active": managed_user.is_active})
    if request.method == "POST" and form.is_valid():
        requested_role = form.cleaned_data["role"]
        requested_active = form.cleaned_data["is_active"]
        if managed_user.is_superuser and requested_role != UserProfile.Role.ADMIN:
            form.add_error("role", "A superuser cannot be demoted from this panel.")
        elif managed_user.is_superuser and not requested_active:
            form.add_error("is_active", "A superuser cannot be deactivated from this panel.")
        elif managed_user == request.user and (requested_role != UserProfile.Role.ADMIN or not requested_active):
            form.add_error(None, "You cannot remove your own active administrator access.")
        elif is_admin_user(managed_user) and requested_role == UserProfile.Role.USER and _admin_count() <= 1:
            form.add_error("role", "The platform must retain at least one administrator.")
        else:
            profile.role = requested_role
            profile.save(update_fields=("role", "updated_at"))
            managed_user.is_active = requested_active
            managed_user.save(update_fields=("is_active",))
            messages.success(request, f"{managed_user.username}'s access was updated.")
            return redirect("admin_panel:user_detail", user_id=managed_user.pk)
    return render(request, "admin_panel/user_detail.html", {"managed_user": managed_user, "managed_role": initial_role, "form": form})


@admin_required
def feedback_list(request):
    feedback = Feedback.objects.select_related("user").order_by("resolved", "-created_at")[:500]
    return render(request, "admin_panel/feedback_list.html", {"feedback_items": feedback})


@admin_required
def toggle_feedback(request, feedback_id):
    if request.method == "POST":
        item = get_object_or_404(Feedback, pk=feedback_id)
        item.resolved = not item.resolved
        item.save(update_fields=("resolved",))
        messages.success(request, "Feedback status updated.")
    return redirect("admin_panel:feedback_list")


@admin_required
def audit_log(request):
    logs = AbbreviationAuditLog.objects.select_related("user", "abbreviation_entry").order_by("-timestamp")[:500]
    return render(request, "admin_panel/audit_log.html", {"logs": logs})
