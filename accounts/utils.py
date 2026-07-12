from .models import UserProfile


def user_role(user):
    if not getattr(user, "is_authenticated", False):
        return None
    if user.is_superuser or user.is_staff:
        return UserProfile.Role.ADMIN
    try:
        return user.profile.role
    except UserProfile.DoesNotExist:
        profile, _ = UserProfile.objects.get_or_create(user=user, defaults={"role": UserProfile.Role.USER})
        return profile.role


def is_admin_user(user):
    return user_role(user) == UserProfile.Role.ADMIN


def is_normal_user(user):
    return bool(getattr(user, "is_authenticated", False)) and not is_admin_user(user)
