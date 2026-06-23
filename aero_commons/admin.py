from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin

from .models import Department, Position

from django.contrib.auth import get_user_model

User = get_user_model()
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


@admin.register(User)
class CustomUserAdmin( UserAdmin):
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

    fieldsets = [
        (None, {"fields": ("username", "password")}),
        (
            "Personal info",
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "first_name_fa",
                    "last_name_fa",
                    "email",
                    "thumbnail",
                    "birth_date",
                )
            },
        ),
        (
            "Organizational info",
            {
                "fields": (
                    "position",
                    "direct_manager",
                    "personnel_code",
                    "identify_code",
                    "last_degree",
                )
            },
        ),
        (
            "Contact info",
            {"fields": ("phone", "address")},
        ),
        (
            "LDAP info",
            {"fields": ("use_ldap", "ldap_id", "cn")},
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    ]

    # LDAP sync action
    actions = ["sync_users_from_ldap"]

    @admin.action(description="🔄 Sync users from LDAP")
    def sync_users_from_ldap(self, request, queryset):
        """
        Execute LDAP sync from Django Admin.
        """
        result = User.sync_from_ldap(dry_run=False)
        messages.success(
            request,
            f"LDAP Sync: Created {result['created']} | Updated {result['updated']}",
        )
