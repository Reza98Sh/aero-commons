from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django_mptt_admin.admin import DjangoMpttAdmin

from .models import Department, Position, CustomUser


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    """
    Admin interface for Department model.
    """

    list_display = ["name"]
    search_fields = ["name"]


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    """
    Admin interface for Position model.
    """

    list_display = ["title_en", "title_fa", "department"]
    list_filter = ["department"]
    search_fields = ["title_en", "title_fa"]


@admin.register(CustomUser)
class CustomUserAdmin(DjangoMpttAdmin, UserAdmin):
    """
    Admin interface for CustomUser model with MPTT tree support.
    """

    # List view configuration
    list_display = [
        "username",
        "email",
        "first_name",
        "last_name",
        "position",
        "is_active",
    ]
    list_filter = ["is_staff", "is_active", "position__department"]
    search_fields = ["username", "first_name", "last_name", "email"]
    ordering = ["username"]


    # LDAP sync action
    actions = ["sync_users_from_ldap"]

    @admin.action(description="🔄 Sync users from LDAP")
    def sync_users_from_ldap(self, request, queryset):
        """
        Execute LDAP sync from Django Admin.
        """
        result = CustomUser.sync_from_ldap(dry_run=False)
        messages.success(
            request,
            f"LDAP Sync: Created {result['created']} | Updated {result['updated']} | Linked {result['linked']}",
        )
