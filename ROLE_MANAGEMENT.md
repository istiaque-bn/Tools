# Role management

## Roles

The platform has two application roles:

- **Admin**: Django superusers, Django staff users, and users whose `UserProfile.role` is `admin`.
- **User**: authenticated accounts that are not Admins. New ordinary accounts receive this role automatically.

Existing accounts are mapped safely by migration: staff and superusers become Admin profiles; all other accounts become User profiles. Django staff and superuser flags remain unchanged.

## Capabilities

Admins can access `/panel/`, manage users, manage the global abbreviation dictionary, review feedback, and inspect abbreviation audit events. Django staff may also open `/admin/`.

Users can access the normal dashboard and tool pages. DOCX-specific permissions remain layered on top of the User role. Personal DOCX session views continue filtering objects by the logged-in user.

## Access helpers

`accounts.utils` provides `is_admin_user`, `is_normal_user`, and `user_role`. `accounts.decorators` provides `admin_required` and `user_required`. Unauthenticated requests redirect to `/login/`; authenticated users without Admin access receive HTTP 403.

## Login redirects

After login, Admins go to `/panel/` and Users go to `/`. A safe, same-host `next` value takes precedence. Already-authenticated users visiting the login page are redirected according to role.

## Admin panel

- `/panel/` and `/panel/dashboard/` — statistics and recent activity
- `/panel/users/` — searchable/filterable user list
- `/panel/users/<id>/` — role and active-status management
- `/panel/feedback/` — feedback review
- `/panel/audit-log/` — abbreviation audit events
- `/tools/docx-abbreviations/dictionary/manage/` — global abbreviation management, linked from the panel sidebar

The sidebar only includes modules that exist in this project. No placeholder book, payment, subscription, notification, or settings modules were added.

## Managing users

An Admin can set an ordinary profile role to Admin or User and activate/deactivate ordinary accounts. Superusers cannot be demoted or deactivated in the custom panel. An Admin cannot remove their own active Admin access, and the platform must retain at least one Admin.

To create a full Django administrator:

```shell
python manage.py createsuperuser
```

To grant only custom-panel Admin access, use `/panel/users/<id>/` and select Admin.

## Navigation

The site navbar shows only the site dashboard, one role-appropriate primary destination, and an account dropdown. Sign out is inside that dropdown. Admin panel pages use a separate responsive sidebar and do not render the site navbar.

## Known limitations

- There is no registration, profile-editing, password-reset, subscription, payment, notification, or content/book module in the current project.
- Profile Admin access does not imply Django staff or superuser access.
- The custom user list is capped at 500 results; filters should be used on larger installations.
