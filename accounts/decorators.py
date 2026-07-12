from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .utils import is_admin_user


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url="login")
        if not is_admin_user(request.user):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return wrapped


def user_required(view_func):
    """Require authentication; admins may also use normal site features."""
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url="login")
        return view_func(request, *args, **kwargs)
    return wrapped
