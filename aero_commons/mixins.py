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
    
    This mixin handles synchronization of user data from an LDAP server
    to the Django CustomUser model. All profile fields are now directly
    on the CustomUser model (UserInfo has been merged into CustomUser).
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
        """
        Create and bind LDAP connection using settings from Django settings.
        
        Returns:
            Connection: Bound LDAP connection object
        """
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
        """
        Fetch LDAP entries using pagination to handle large directories.
        
        Args:
            conn: LDAP connection object
            progress_cb: Optional callback function for progress updates
            
        Returns:
            list: List of LDAP entry objects
        """
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
        All user data (including profile info) is now consolidated into
        a single user_data dict since UserInfo has been merged into CustomUser.
        
        Args:
            entry: LDAP entry object
            
        Returns:
            dict: Normalized data dictionary or None if entry is invalid
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

        def safe_unique_str(attr_name):
            """
            For unique fields, return None instead of empty string.
            Multiple NULLs are allowed in unique columns, but multiple empty strings are not.
            
            Args:
                attr_name: Name of the LDAP attribute
                
            Returns:
                String value or None
            """
            return safe_str(attr_name, default=None, allow_none=True)

        # Build email with fallback
        email = safe_str("mail", default="")
        if not email:
            email_domain = getattr(settings, "CUSTOM_USERS_EMAIL_DOMAIN", "mapnaaero.com")
            email = f"{username}@{email_domain}"

        # Build consolidated user data (includes former UserInfo fields)
        user_data = {
            # Authentication and LDAP fields
            "email": email,
            "first_name": safe_str("givenName", default=""),
            "last_name": safe_str("sn", default=""),
            "use_ldap": True,
            "ldap_id": ldap_id,
            "cn": safe_str("cn", default="", allow_none=True),
            
            # Profile fields (formerly in UserInfo)
            "phone": safe_str("telephoneNumber", default=""),
            "personnel_code": safe_unique_str("postalCode"),  # Can be None (unique field)
        }

        return {
            "username": username,
            "user_data": user_data,
            "manager_dn": safe_str("manager", default="", allow_none=True),
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
        
        Since UserInfo is merged into CustomUser, all fields are written
        directly to the CustomUser model.
        """
        from aero_commons.models import CustomUser, Department, Position

        if dry_run:
            return None

        with transaction.atomic():
            # -------------------------
            # Create or update user
            # -------------------------
            user, created = CustomUser.objects.update_or_create(
                username=record["username"],
                defaults=record["user_data"],
            )

            # -------------------------
            # Department & Position
            # -------------------------
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

            # -------------------------
            # Handle thumbnail
            # -------------------------
            if record.get("thumbnail"):
                try:
                    if user.thumbnail:
                        user.thumbnail.delete(save=False)
                    user.thumbnail.save(
                        f"{user.username}.jpg",
                        ContentFile(record["thumbnail"]),
                        save=False,
                    )
                except Exception as e:
                    logger.error(
                        f"Error saving thumbnail for {user.username}: {e}"
                    )

            user.save()

        return created

    # -------------------------
    # MAIN PUBLIC API
    # -------------------------
    @classmethod
    def sync_from_ldap(cls, dry_run=False, callback=None):
        """
        Public API for LDAP sync.
        
        Returns statistics about created and updated users.
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
        """
        Link users to their direct managers based on LDAP manager DN.
        """
        from aero_commons.models import CustomUser

        if dry_run:
            return

        for username, manager_dn in manager_map.items():
            if not manager_dn:
                continue

            try:
                manager_cn = manager_dn.split(",")[0].split("=")[1]
                user = CustomUser.objects.get(username=username)
                manager = CustomUser.objects.filter(
                    cn__iexact=manager_cn
                ).first()

                if manager and user.direct_manager != manager:
                    user.direct_manager = manager
                    user.save()
            except Exception:
                # Fail silently but log for debugging
                logger.exception(
                    f"Failed to link manager for user '{username}'"
                )
