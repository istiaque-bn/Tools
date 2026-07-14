from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


@receiver(post_save, sender=get_user_model())
def ensure_user_profile(sender, instance, created, **kwargs):
    default_role = (
        UserProfile.Role.ADMIN
        if instance.is_staff or instance.is_superuser
        else UserProfile.Role.USER
    )
    UserProfile.objects.get_or_create(user=instance, defaults={"role": default_role})
    checker_group = Group.objects.filter(name="DOCX Abbreviation Users").first()
    if checker_group and not instance.groups.filter(pk=checker_group.pk).exists():
        instance.groups.add(checker_group)
