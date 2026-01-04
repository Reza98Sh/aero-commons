import uuid
import logging

from django.conf import settings
from django.db import transaction
from django.core.files.base import ContentFile
from ldap3 import Server, Connection, ALL, SUBTREE

logger = logging.getLogger(__name__)


class LDAPSyncMixin:
    """
    Provides LDAP synchronization logic for CustomUser.
    """

    LDAP_PAGE_SIZE = 1000

    LDAP_ATTRIBUTES = [
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

    # -------------------------
    # LDAP CONNECTION
    # -------------------------
    @classmethod
    def get_ldap_connection(cls):
        """Create and bind LDAP connection."""
        server = Server(settings.LDAP_HOST, get_info=ALL)
        return Connection(
            server,
            user=settings.LDAP_ADMIN_USER,
            password=settings.LDAP_ADMIN_PASSWORD,
            auto_bind=True,
        )

    # -------------------------
    # FETCH LDAP ENTRIES
    # -------------------------
    @classmethod
    def fetch_ldap_entries(cls, conn, progress_cb=None):
        """Fetch LDAP entries using pagination."""
        entries = []
        page_size = cls.LDAP_PAGE_SIZE

        conn.search(
            search_base=settings.LDAP_BASE_DN,
            search_filter="(objectCategory=Person)",
            search_scope=SUBTREE,
            attributes=cls.LDAP_ATTRIBUTES,
            paged_size=page_size,
        )

        entries.extend(conn.entries or [])

        controls = conn.result.get("controls", {})
        while "1.2.840.113556.1.4.319" in controls:
            cookie = controls["1.2.840.113556.1.4.319"]["value"]["cookie"]
            if not cookie:
                break

            if progress_cb:
                progress_cb(f"Fetching next LDAP page... ({len(entries)})")

            conn.search(
                search_base=settings.LDAP_BASE_DN,
                search_filter="(objectCategory=Person)",
                search_scope=SUBTREE,
                attributes=cls.LDAP_ATTRIBUTES,
                paged_size=page_size,
                paged_cookie=cookie,
            )

            entries.extend(conn.entries or [])
            controls = conn.result.get("controls", {})

        return entries

    # -------------------------
    # EXTRACT LDAP RECORD
    # -------------------------
    @classmethod
    def extract_entry_data(cls, entry):
        """
        Convert LDAP entry to normalized dict.
        Handles empty values properly to avoid unique constraint violations.
        """
        if not hasattr(entry, "sAMAccountName"):
            return None

        username = str(entry.sAMAccountName)

        # Extract LDAP UUID
        ldap_id = None
        if hasattr(entry, "objectGUID") and entry.objectGUID:
            try:
                ldap_id = uuid.UUID(str(entry.objectGUID))
            except ValueError:
                pass

        # Extract thumbnail
        thumbnail = None
        if hasattr(entry, "thumbnailPhoto") and entry.thumbnailPhoto:
            try:
                thumbnail = entry.thumbnailPhoto.value
            except Exception:
                pass

        # Helper function to safely extract string value
        def safe_str(attr_name, default="", allow_none=False):
            """
            Safely extract string value from LDAP entry.
            
            Args:
                attr_name: Name of the LDAP attribute
                default: Default value if attribute is missing or empty
                allow_none: If True and value is empty, return None instead of default
            
            Returns:
                String value, default value, or None based on parameters
            """
            if not hasattr(entry, attr_name):
                return None if allow_none else default
            
            value = getattr(entry, attr_name)
            
            # Handle None
            if value is None:
                return None if allow_none else default
            
            # Handle empty list (LDAP often returns [] for missing values)
            if isinstance(value, (list, tuple)) and len(value) == 0:
                return None if allow_none else default
            
            # Convert to string
            str_value = str(value).strip()
            
            # Handle string representations of empty values
            if str_value in ("", "[]", "None"):
                return None if allow_none else default
            
            return str_value

        # Helper for nullable unique fields (like personnel_code)
        def safe_unique_str(attr_name):
            """
            For unique fields, return None instead of empty string.
            Multiple NULLs are allowed in unique columns, but multiple empty strings are not.
            """
            return safe_str(attr_name, default=None, allow_none=True)

        # Build user data - IMPORTANT: first_name and last_name MUST have string defaults
        email = safe_str("mail", default="")
        if not email:
            email = f"{username}@mapnaaero.com"

        user_data = {
            "email": email,
            "first_name": safe_str("givenName", default=""),  # Empty string, NOT None
            "last_name": safe_str("sn", default=""),          # Empty string, NOT None
            "use_ldap": True,
            "ldap_id": ldap_id,
        }

        # Build info data - personnel_code is unique, so use safe_unique_str
        info_data = {
            "phone": safe_str("telephoneNumber", default=""),
            "personnel_code": safe_unique_str("postalCode"),  # Can be None (unique field)
        }

        return {
            "username": username,
            "cn": safe_str("cn", default="", allow_none=True),
            "manager_dn": safe_str("manager", default="", allow_none=True),
            "user_data": user_data,
            "info_data": info_data,
            "position_title": safe_str("title", default="", allow_none=True),
            "department_name": safe_str("department", default="", allow_none=True),
            "thumbnail": thumbnail,
        }


    # -------------------------
    # SYNC SINGLE USER
    # -------------------------
    @classmethod
    def sync_single_user(cls, record, dry_run=False):
        """
        Create or update one user with proper handling of unique fields.
        """
        from aero_commons.models import CustomUser, UserInfo, Department, Position

        if dry_run:
            return None

        with transaction.atomic():
            # Create or update user
            user, created = CustomUser.objects.update_or_create(
                username=record["username"],
                defaults=record["user_data"],
            )

            user.cn = record["cn"]
            user.save()

            # Department & Position
            if record["position_title"]:
                dept = None
                if record["department_name"]:
                    dept, _ = Department.objects.get_or_create(
                        name=record["department_name"]
                    )
                
                position, _ = Position.objects.get_or_create(
                    title_en=record["position_title"],
                    defaults={"department": dept},
                )
                
                if user.position != position:
                    user.position = position
                    user.save()

            # Handle UserInfo with special care for unique personnel_code
            info_data = record["info_data"].copy()
            personnel_code = info_data.get("personnel_code")
            
            # If personnel_code is not None and not empty, check for conflicts
            if personnel_code:
                # Check if another user already has this personnel_code
                existing_info = UserInfo.objects.filter(
                    personnel_code=personnel_code
                ).exclude(user=user).first()
                
                if existing_info:
                    # Another user has this code, log warning and set to None
                    logger.warning(
                        f"personnel_code '{personnel_code}' already exists for user "
                        f"'{existing_info.user.username}', skipping for '{user.username}'"
                    )
                    info_data["personnel_code"] = None

            # Now safely update or create UserInfo
            info, _ = UserInfo.objects.update_or_create(
                user=user,
                defaults=info_data,
            )

            # Thumbnail
            if record.get("thumbnail"):
                try:
                    if info.thumbnail:
                        info.thumbnail.delete(save=False)
                    info.thumbnail.save(
                        f"{user.username}.jpg",
                        ContentFile(record["thumbnail"]),
                        save=True,
                    )
                except Exception as e:
                    logger.error(f"Error saving thumbnail for {user.username}: {e}")

        return created

    # -------------------------
    # MAIN PUBLIC API
    # -------------------------
    @classmethod
    def sync_from_ldap(cls, dry_run=False, callback=None):
        """
        Public API for LDAP sync.
        """
        created = updated = 0
        manager_map = {}

        conn = cls.get_ldap_connection()
        try:
            entries = cls.fetch_ldap_entries(conn, callback)

            for entry in entries:
                record = cls.extract_entry_data(entry)
                if not record:
                    continue

                manager_map[record["username"]] = record["manager_dn"]
                result = cls.sync_single_user(record, dry_run)

                if result is True:
                    created += 1
                elif result is False:
                    updated += 1
        finally:
            conn.unbind()

        cls._link_managers(manager_map, dry_run)

        return {
            "created": created,
            "updated": updated,
            "total": len(entries),
        }

    # -------------------------
    # LINK MANAGERS
    # -------------------------
    @classmethod
    def _link_managers(cls, manager_map, dry_run):
        from aero_commons.models import CustomUser

        for username, manager_dn in manager_map.items():
            if not manager_dn or dry_run:
                continue

            try:
                manager_cn = manager_dn.split(",")[0].split("=")[1]
                user = CustomUser.objects.get(username=username)
                manager = CustomUser.objects.filter(cn__iexact=manager_cn).first()

                if manager and user.direct_manager != manager:
                    user.direct_manager = manager
                    user.save()
            except Exception:
                pass
