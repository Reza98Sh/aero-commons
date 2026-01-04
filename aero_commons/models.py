"""
Custom User Models for Django.
Includes Department, Position, CustomUser with MPTT support, and UserInfo.
"""
import uuid

from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from mptt.models import MPTTModel, TreeForeignKey
from mptt.managers import TreeManager
from django.db import transaction
from django.core.files.base import ContentFile
from django.conf import settings
from ldap3 import Server, Connection, ALL, SUBTREE



class Department(models.Model):
    """
    Represents a department within the organization.
    
    Attributes:
        name: Unique name of the department
    """
    
    name = models.CharField(
        verbose_name="Department Name",
        max_length=100,
        unique=True,
        help_text="Enter the unique name of the department",
    )

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Department"
        verbose_name_plural = "Departments"
        ordering = ["name"]


class Position(models.Model):
    """
    Represents a position or role within a department.
    
    Attributes:
        title_en: English title of the position (required, unique)
        title_fa: Persian/Farsi title of the position (optional)
        department: Foreign key to the related department
    """
    
    title_en = models.CharField(
        verbose_name="Title (English)",
        max_length=100,
        unique=True,
        help_text="Enter the English title of this position",
    )
    
    title_fa = models.CharField(
        verbose_name="Title (Farsi)",
        max_length=100,
        null=True,
        blank=True,
        help_text="Enter the Farsi/Persian title of this position",
    )
    
    department = models.ForeignKey(
        Department,
        verbose_name="Department",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="positions",
        help_text="Select the department this position belongs to",
    )

    def __str__(self):
        return self.title_en

    class Meta:
        verbose_name = "Position"
        verbose_name_plural = "Positions"
        ordering = ["title_en"]


class CustomUserManager(TreeManager, UserManager):
    """
    A hybrid manager that combines MPTT Tree methods with Django Auth methods.
    
    This manager enables both hierarchical queries (ancestors, descendants)
    and standard user authentication operations.
    """
    
    def get_queryset(self):
        """
        Return a TreeQuerySet that supports both MPTT and standard operations.
        """
        return super().get_queryset()


class CustomUser(AbstractUser, MPTTModel):
    """
    Custom user model extending Django's AbstractUser with MPTT support.
    
    Features:
        - LDAP authentication support
        - Organizational hierarchy (direct manager relationship)
        - Position and department associations
        - Automatic email generation
    
    Attributes:
        ldap_id: UUID from LDAP server (optional)
        use_ldap: Flag indicating if user authenticates via LDAP
        cn: Common Name from LDAP
        position: Foreign key to user's position
        direct_manager: Self-referential foreign key for org hierarchy
    """
    
    ldap_id = models.UUIDField(
        verbose_name="LDAP ID",
        null=True,
        blank=True,
        unique=True,
        help_text="Unique identifier from LDAP server",
    )
    
    use_ldap = models.BooleanField(
        verbose_name="Use LDAP",
        default=False,
        help_text="Indicates whether the user authenticates via LDAP",
    )
    
    cn = models.CharField(
        verbose_name="Common Name",
        max_length=255,
        null=True,
        blank=True,
        help_text="Common Name (CN) from LDAP",
    )
    
    position = models.ForeignKey(
        Position,
        verbose_name="Position",
        on_delete=models.SET_NULL,
        related_name="users",
        null=True,
        blank=True,
        help_text="Select the organizational position for this user",
    )
    
    direct_manager = TreeForeignKey(
        "self",
        verbose_name="Direct Manager",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subordinates",
        help_text="Select the direct manager/supervisor for this user",
    )

    # Use the custom hybrid manager
    objects = CustomUserManager()

    class MPTTMeta:
        """
        MPTT configuration for hierarchical structure.
        """
        parent_attr = "direct_manager"
        order_insertion_by = ["username"]

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    def save(self, *args, **kwargs):
        """
        Override save method to:
        - Set an unusable password for LDAP-based users
        - Auto-generate corporate email if none provided
        
        Args:
            *args: Variable length argument list
            **kwargs: Arbitrary keyword arguments
        """
        # LDAP users should not have usable passwords
        if self.use_ldap:
            self.set_unusable_password()
        
        # Generate default email if not provided
        if not self.email:
            email_domain = getattr(
                settings, 
                "CUSTOM_USERS_EMAIL_DOMAIN", 
                "example.com"
            )
            self.email = f"{self.username}@{email_domain}"
        
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username

    
    @classmethod
    def sync_from_ldap(cls, dry_run=False):
        """
        Synchronize users from LDAP into database.
        Can be safely executed from Django Admin.
        """

        created_count = 0
        updated_count = 0
        linked_count = 0
        user_manager_map = {}

        server = Server(settings.LDAP_HOST, get_info=ALL)
        conn = Connection(
            server,
            user=settings.LDAP_ADMIN_USER,
            password=settings.LDAP_ADMIN_PASSWORD,
            auto_bind=True,
        )

        page_size = 1000
        search_filter = "(objectCategory=Person)"

        attributes = [
            "sAMAccountName",
            "mail",
            "givenName",
            "sn",
            "objectGUID",
            "telephoneNumber",
            "postalCode",
            "title",
            "department",
            "manager",
            "cn",
            "thumbnailPhoto",
        ]

        conn.search(
            settings.LDAP_BASE_DN,
            search_filter,
            SUBTREE,
            attributes=attributes,
            paged_size=page_size,
        )

        entries = list(conn.entries)

        controls = conn.result.get("controls", {})
        while "1.2.840.113556.1.4.319" in controls:
            cookie = controls["1.2.840.113556.1.4.319"]["value"]["cookie"]
            if not cookie:
                break

            conn.search(
                settings.LDAP_BASE_DN,
                search_filter,
                SUBTREE,
                attributes=attributes,
                paged_size=page_size,
                paged_cookie=cookie,
            )
            entries.extend(conn.entries)
            controls = conn.result.get("controls", {})

        for entry in entries:
            if not hasattr(entry, "sAMAccountName"):
                continue

            username = str(entry.sAMAccountName)
            user_manager_map[username] = str(entry.manager) if hasattr(entry, "manager") else None

            ldap_uuid = None
            if hasattr(entry, "objectGUID") and entry.objectGUID:
                try:
                    ldap_uuid = uuid.UUID(str(entry.objectGUID))
                except ValueError:
                    pass

            if dry_run:
                continue

            with transaction.atomic():
                user, created = cls.objects.update_or_create(
                    username=username,
                    defaults={
                        "email": str(entry.mail) if entry.mail else f"{username}@mapnaaero.com",
                        "first_name": str(entry.givenName) if entry.givenName else "",
                        "last_name": str(entry.sn) if entry.sn else "",
                        "use_ldap": True,
                        "ldap_id": ldap_uuid,
                        "cn": str(entry.cn) if entry.cn else None,
                    },
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

                department = None
                if hasattr(entry, "department") and entry.department:
                    department, _ = Department.objects.get_or_create(name=str(entry.department))

                if hasattr(entry, "title") and entry.title:
                    position, _ = Position.objects.get_or_create(
                        title_en=str(entry.title),
                        defaults={"department": department},
                    )
                    user.position = position
                    user.save()

                info, _ = UserInfo.objects.update_or_create(
                    user=user,
                    defaults={
                        "phone": str(entry.telephoneNumber) if entry.telephoneNumber else "",
                        "personnel_code": str(entry.postalCode) if entry.postalCode else None,
                    },
                )

                if hasattr(entry, "thumbnailPhoto") and entry.thumbnailPhoto:
                    photo = entry.thumbnailPhoto.value
                    if photo:
                        info.thumbnail.save(
                            f"{username}.jpg",
                            ContentFile(photo),
                            save=True,
                        )

        conn.unbind()

        # Link managers
        for username, manager_dn in user_manager_map.items():
            if not manager_dn or dry_run:
                continue

            try:
                manager_cn = manager_dn.split(",")[0].split("=")[1]
                employee = cls.objects.get(username=username)
                manager = cls.objects.filter(cn__iexact=manager_cn).first()

                if manager and manager != employee:
                    employee.direct_manager = manager
                    employee.save()
                    linked_count += 1
            except Exception:
                continue

        return {
            "created": created_count,
            "updated": updated_count,
            "linked": linked_count,
        }
        


class UserInfo(models.Model):
    """
    Stores additional profile information for a CustomUser.
    
    This model contains personal and HR-related information that is
    separated from the main user model for better organization.
    
    Attributes:
        thumbnail: Profile picture
        identify_code: National or organizational ID
        last_degree: Highest academic degree
        address: Mailing address
        phone: Contact phone number
        birth_date: Date of birth
        personnel_code: Unique personnel/employee code
        user: One-to-one relation to CustomUser
    """
    
    thumbnail = models.ImageField(
        verbose_name="Profile Picture",
        upload_to="thumbs/%Y/%m/",
        null=True,
        blank=True,
        help_text="Upload a profile picture",
    )
    
    identify_code = models.CharField(
        verbose_name="Identification Code",
        max_length=10,
        null=True,
        blank=True,
        help_text="Enter the national or organizational ID code",
    )
    
    last_degree = models.CharField(
        verbose_name="Last Academic Degree",
        max_length=120,
        null=True,
        blank=True,
        help_text="Enter the highest academic degree held by the user",
    )
    
    address = models.TextField(
        verbose_name="Address",
        null=True,
        blank=True,
        help_text="Enter the full mailing address",
    )
    
    phone = models.CharField(
        verbose_name="Phone Number",
        max_length=12,
        null=True,
        blank=True,
        help_text="Enter the contact phone number",
    )
    
    birth_date = models.DateField(
        verbose_name="Birth Date",
        null=True,
        blank=True,
        help_text="Enter the user's date of birth",
    )
    
    personnel_code = models.CharField(
        verbose_name="Personnel Code",
        max_length=10,
        unique=True,
        null=True,
        blank=True,
        help_text="Unique personnel/employee code",
    )
    
    user = models.OneToOneField(
        CustomUser,
        verbose_name="User",
        on_delete=models.CASCADE,
        related_name="info",
        help_text="The user to which this profile belongs",
    )

    def __str__(self):
        return f"Profile: {self.user.username}"

    class Meta:
        verbose_name = "User Info"
        verbose_name_plural = "User Infos"
