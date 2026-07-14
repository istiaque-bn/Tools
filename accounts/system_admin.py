import csv
import io
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.db import connection


def _postgres_command(name):
    if connection.vendor != "postgresql":
        raise ValueError(f"{name} is available only when PostgreSQL is active.")
    executable = shutil.which(name)
    config = connection.settings_dict
    env = os.environ.copy()
    env["PGPASSWORD"] = str(config.get("PASSWORD") or "")
    if executable:
        args = [
            executable,
            "--host",
            str(config.get("HOST") or "localhost"),
            "--port",
            str(config.get("PORT") or "5432"),
            "--username",
            str(config.get("USER") or ""),
            "--dbname",
            str(config["NAME"]),
        ]
        return args, env, False
    docker = shutil.which("docker")
    if docker and (Path(settings.BASE_DIR) / "compose.yaml").exists():
        args = [
            docker,
            "compose",
            "exec",
            "-T",
            "postgres",
            name,
            "--username",
            str(config.get("USER") or ""),
            "--dbname",
            str(config["NAME"]),
        ]
        return args, env, True
    raise ValueError(
        f"The PostgreSQL {name} utility is not installed on the application server."
    )


def create_postgres_backup():
    args, env, docker = _postgres_command("pg_dump")
    result = subprocess.run(
        args + ["--format=custom", "--no-owner", "--no-acl"],
        env=env,
        cwd=settings.BASE_DIR if docker else None,
        capture_output=True,
        timeout=300,
        check=False,
    )
    if result.returncode or not result.stdout.startswith(b"PGDMP"):
        raise ValueError("PostgreSQL could not create a valid database backup.")
    return io.BytesIO(result.stdout)


def restore_postgres_backup(upload):
    if not upload or upload.size < 5 or upload.size > 500 * 1024 * 1024:
        raise ValueError("Choose a PostgreSQL custom backup no larger than 500 MB.")
    header = upload.read(5)
    upload.seek(0)
    if header != b"PGDMP":
        raise ValueError("The uploaded file is not a PostgreSQL custom-format backup.")
    args, env, docker = _postgres_command("pg_restore")
    connection.close()
    if docker:
        result = subprocess.run(
            args
            + [
                "--clean",
                "--if-exists",
                "--no-owner",
                "--no-acl",
                "--single-transaction",
            ],
            input=upload.read(),
            env=env,
            cwd=settings.BASE_DIR,
            capture_output=True,
            timeout=600,
            check=False,
        )
    else:
        with tempfile.NamedTemporaryFile(suffix=".backup") as temporary:
            for chunk in upload.chunks():
                temporary.write(chunk)
            temporary.flush()
            result = subprocess.run(
                args
                + [
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    "--no-acl",
                    "--single-transaction",
                    temporary.name,
                ],
                env=env,
                capture_output=True,
                timeout=600,
                check=False,
            )
    if result.returncode:
        raise ValueError(
            "PostgreSQL could not restore the backup. The existing database was left unchanged."
        )


def system_health():
    cached = cache.get("admin:system-health:v1")
    if cached:
        return cached
    checks = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        checks["database"] = {
            "ok": True,
            "detail": f"{connection.vendor.title()} connected",
        }
    except Exception:
        checks["database"] = {"ok": False, "detail": "Database connection failed"}
    from home_ai.document_conversion import _libreoffice_binary

    libreoffice = _libreoffice_binary()
    checks["libreoffice"] = {
        "ok": bool(libreoffice),
        "detail": "Available" if libreoffice else "Not installed",
    }
    root = Path(settings.DOCX_ABBREVIATION_TEMP_ROOT)
    try:
        root.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(root)
        checks["storage"] = {
            "ok": os.access(root, os.W_OK),
            "detail": f"{usage.free / (1024**3):.1f} GB free",
        }
    except OSError:
        checks["storage"] = {"ok": False, "detail": "Temporary storage unavailable"}
    try:
        request = Request(
            "https://api.dictionaryapi.dev/api/v2/entries/en/hello",
            method="HEAD",
            headers={"User-Agent": "NecessaryTools/1.0"},
        )
        with urlopen(request, timeout=2) as response:
            reachable = response.status < 500
        checks["dictionary"] = {
            "ok": reachable,
            "detail": "Online provider reachable"
            if reachable
            else "Provider unavailable",
        }
    except HTTPError as exc:
        checks["dictionary"] = {
            "ok": exc.code < 500,
            "detail": "Provider reachable"
            if exc.code < 500
            else "Provider unavailable",
        }
    except (URLError, TimeoutError, OSError):
        checks["dictionary"] = {
            "ok": False,
            "detail": "Offline or provider unavailable",
        }
    cache.set("admin:system-health:v1", checks, 60)
    return checks


def audit_csv(logs, sessions):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("event_type", "action", "user", "item", "timestamp", "details"))
    for log in logs:
        writer.writerow(
            (
                "abbreviation",
                log.action,
                log.user.username if log.user else "System",
                str(log.abbreviation_entry or "Deleted entry"),
                log.timestamp.isoformat(),
                str(log.new_value or log.previous_value or ""),
            )
        )
    for session in sessions:
        writer.writerow(
            (
                "document",
                session.status,
                session.user.username,
                session.original_filename,
                session.created_at.isoformat(),
                f"{session.operation_type}; {session.accepted_count} accepted",
            )
        )
    return io.BytesIO(output.getvalue().encode("utf-8-sig"))
