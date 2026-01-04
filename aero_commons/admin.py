from django.contrib import admin
from .models import Department, Position, CustomUser, UserInfo
from django.contrib import admin, messages

from django.contrib.auth.admin import UserAdmin

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    """
    Admin interface for Department model.
    """
    list_display = ['name']
    search_fields = ['name']


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    """
    Admin interface for Position model.
    """
    list_display = ['title_en', 'title_en', 'department']
    list_filter = ['department']
    search_fields = ['title_en', 'title_en']


class UserInfoInline(admin.StackedInline):
    """
    Inline admin for UserInfo to show within CustomUser admin.
    """
    model = UserInfo
    can_delete = False
    verbose_name_plural = 'User Information'
    fk_name = 'user'



from django_mptt_admin.admin import DjangoMpttAdmin


@admin.register(CustomUser)
class CustomUserAdmin(DjangoMpttAdmin, UserAdmin):
    """
    Admin interface for CustomUser model with MPTT tree support.
    """
    
    inlines = [UserInfoInline]
    list_per_page = 100
    
    # Filters in the sidebar
    list_filter = [
        'is_staff',
        'is_superuser',
        'is_active',
        'position__department',
    ]
    
    # Search fields
    search_fields = [
        'username',
        'first_name',
        'last_name',
        'email',
        'info__personnel_code',
    ]
    
    # Custom fieldsets for add/edit forms
    fieldsets = (
        (None, {
            'fields': ('username', 'password')
        }),
        ('Personal Info', {
            'fields': ('first_name', 'last_name', 'email','cn')
        }),
        ('Organizational Info', {
            'fields': ('position', 'direct_manager', 'use_ldap')
        }),
        ('Permissions', {
            'fields': (
                'is_active',
                'is_staff',
                'is_superuser',
                'groups',
                'user_permissions',
            ),
            'classes': ('collapse',),
        }),
        ('Important Dates', {
            'fields': ('last_login', 'date_joined'),
            'classes': ('collapse',),
        }),
    )
    
    # Fieldsets for adding a new user
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'username',
                'password1',
                'password2',
                'email',
                'position',
                'direct_manager',
                'use_ldap',
                'is_staff',
                'is_active',
            ),
        }),
    )
    
    # Ordering in the list view
    ordering = ['username']
    
    # Read-only fields
    readonly_fields = ['last_login', 'date_joined']
    
    
    actions = ["sync_users_from_ldap"]

    @admin.action(description="🔄 Sync users from LDAP")
    def sync_users_from_ldap(self, request, queryset):
        """
        Execute LDAP sync directly from Django Admin.
        Selection is ignored – whole LDAP will be synced.
        """

        result = CustomUser.sync_from_ldap(dry_run=False)

        messages.success(
            request,
            f"LDAP Sync completed | "
            f"Created: {result['created']} | "
            f"Updated: {result['updated']} | "
            f"Managers linked: {result['linked']}"
        )



@admin.register(UserInfo)
class UserInfoAdmin(admin.ModelAdmin):
    """
    Admin interface for UserInfo model.
    """
    list_display = ['user',   'personnel_code', 'phone']
    search_fields = [ 'personnel_code', 'identify_code', 'user__username']
    list_filter = ['last_degree']
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('user',  'identify_code', 'birth_date')
        }),
        ('Contact Information', {
            'fields': ('phone', 'address')
        }),
        ('Professional Information', {
            'fields': ('personnel_code', 'last_degree')
        }),
    )
