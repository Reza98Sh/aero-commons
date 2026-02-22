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
        Fetch LDAP entries from both active and inactive OUs using pagination.

        Args:
            conn: LDAP connection object
            progress_cb: Optional callback function for progress updates

        Returns:
            list: List of tuples (entry, is_active) where is_active indicates
                if the entry came from active or inactive OU
        """
        entries = []
        page_size = cls.LDAP_PAGE_SIZE

        # Define search bases - active and inactive users
        search_bases = [
            (settings.LDAP_BASE_DN, True),  # Active users
        ]

        # Add inactive users DN if configured
        inactive_dn = getattr(settings, "LDAP_INACTIVE_USERS_DN", None)
        if inactive_dn:
            search_bases.append((inactive_dn, False))  # Inactive users

        # Fetch from each search base
        for search_base, is_active in search_bases:
            if progress_cb:
                status = "active" if is_active else "inactive"
                progress_cb(f"Fetching {status} users from {search_base}...")

            # Initial search
            conn.search(
                search_base=search_base,
                search_filter="(objectCategory=Person)",
                search_scope=SUBTREE,
                attributes=cls.LDAP_ATTRIBUTES,
                paged_size=page_size,
            )

            # Add entries with their active status
            for entry in conn.entries or []:
                entries.append((entry, is_active))

            # Handle pagination
            controls = conn.result.get("controls", {})
            while "1.2.840.113556.1.4.319" in controls:
                cookie = controls["1.2.840.113556.1.4.319"]["value"]["cookie"]
                if not cookie:
                    break

                if progress_cb:
                    status = "active" if is_active else "inactive"
                    progress_cb(
                        f"Fetching next page of {status} users... ({len(entries)})"
                    )

                conn.search(
                    search_base=search_base,
                    search_filter="(objectCategory=Person)",
                    search_scope=SUBTREE,
                    attributes=cls.LDAP_ATTRIBUTES,
                    paged_size=page_size,
                    paged_cookie=cookie,
                )

                # Add entries with their active status
                for entry in conn.entries or []:
                    entries.append((entry, is_active))

                controls = conn.result.get("controls", {})

        return entries

    # -------------------------
    # EXTRACT LDAP RECORD
    # -------------------------
    @classmethod
    def extract_entry_data(cls, entry, is_active=True):
        """
        Convert LDAP entry to normalized dict.

        Args:
            entry: LDAP entry object
            is_active: Boolean indicating if user is from active or inactive OU

        Returns:
            dict: Normalized data dictionary or None if entry is invalid
        """
        if not hasattr(entry, "sAMAccountName"):
            return None

        username = str(entry.sAMAccountName).lower()

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
            """Safely extract string value from LDAP entry."""
            if not hasattr(entry, attr_name):
                return None if allow_none else default

            value = getattr(entry, attr_name)

            if value is None:
                return None if allow_none else default

            if isinstance(value, (list, tuple)) and len(value) == 0:
                return None if allow_none else default

            str_value = str(value).strip()

            if str_value in ("", "[]", "None"):
                return None if allow_none else default

            return str_value

        def safe_unique_str(attr_name):
            """For unique fields, return None instead of empty string."""
            return safe_str(attr_name, default=None, allow_none=True)

        # Build email with fallback
        email = safe_str("mail", default="")
        if not email:
            email_domain = getattr(
                settings, "CUSTOM_USERS_EMAIL_DOMAIN", "mapnaaero.com"
            )
            email = f"{username}@{email_domain}"

        # Build consolidated user data
        user_data = {
            # Authentication and LDAP fields
            "email": email,
            "first_name": safe_str("givenName", default=""),
            "last_name": safe_str("sn", default=""),
            "use_ldap": True,
            "username": username,
            "cn": safe_str("cn", default="", allow_none=True),
            "is_active": is_active,
            # Profile fields
            "phone": safe_str("telephoneNumber", default=""),
            "personnel_code": safe_unique_str("postalCode"),
        }

        return {
            "ldap_id": ldap_id,
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
            # Handle duplicate personnel_code before save
            # -------------------------
            personnel_code = record["user_data"].get("personnel_code")

            if personnel_code:
                # Check if another user has this personnel_code
                existing_user_with_code = (
                    CustomUser.objects.filter(personnel_code=personnel_code)
                    .exclude(username=record["ldap_id"])
                    .first()
                )

                if existing_user_with_code:
                    # Option 1: Clear the old user's personnel_code
                    logger.warning(
                        f"Personnel code '{personnel_code}' already exists for user "
                        f"'{existing_user_with_code.username}'. Clearing it and assigning "
                        f"to '{record['ldap_id']}'."
                    )
                    existing_user_with_code.personnel_code = None
                    existing_user_with_code.save(update_fields=["personnel_code"])

                    # Option 2: Or skip updating personnel_code for current user
                    # record["user_data"]["personnel_code"] = None

            # -------------------------
            # Create or update user
            # -------------------------

            # Build base defaults (fields that always update)
            update_defaults = {
                k: v
                for k, v in record["user_data"].items()
                if k not in ("first_name", "last_name")
            }

            # Fields only set on creation, never updated
            create_only_fields = {
                "first_name": record["user_data"].get("first_name", ""),
                "last_name": record["user_data"].get("last_name", ""),
            }

            user, created = CustomUser.objects.update_or_create(
                ldap_id=record["ldap_id"],
                defaults=update_defaults,
                create_defaults={
                    **update_defaults,
                    **create_only_fields,
                },  # merged for new records
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
                    logger.error(f"Error saving thumbnail for {user.username}: {e}")

            user.save()

        return created

    # -------------------------
    # MAIN PUBLIC API
    # -------------------------
    @classmethod
    def sync_from_ldap(cls, dry_run=False, callback=None):
        """
        Public API for LDAP sync.

        Returns statistics about created and updated users from both active
        and inactive OUs.
        """
        created = updated = 0
        manager_map = {}

        conn = cls.get_ldap_connection()
        try:
            # Fetch entries from both active and inactive OUs
            entries = cls.fetch_ldap_entries(conn, callback)

            for entry, is_active in entries:
                # Extract entry data with active status
                record = cls.extract_entry_data(entry, is_active)
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
        Handles circular references and self-references gracefully.
        """
        from aero_commons.models import CustomUser
        from mptt.exceptions import InvalidMove

        if dry_run:
            return

        for username, manager_dn in manager_map.items():
            if not manager_dn:
                continue

            try:
                manager_cn = manager_dn.split(",")[0].split("=")[1]
                user = CustomUser.objects.get(username=username)
                manager = CustomUser.objects.filter(cn__iexact=manager_cn).first()

                # Skip if manager not found
                if not manager:
                    continue

                # Skip if trying to set user as their own manager
                if manager.pk == user.pk:
                    logger.warning(
                        f"Skipping self-reference: User '{username}' cannot be their own manager."
                    )
                    continue

                # Skip if manager is already set correctly
                if user.direct_manager == manager:
                    continue

                # Check for circular reference: manager should not be a descendant of user
                # This prevents A -> B -> C -> A type cycles
                if manager.is_descendant_of(user, include_self=True):
                    logger.warning(
                        f"Skipping circular reference: '{manager.username}' is a descendant of '{username}'."
                    )
                    continue

                user.direct_manager = manager
                user.save()

            except InvalidMove as e:
                # Handle any remaining MPTT invalid move errors
                logger.warning(
                    f"InvalidMove error for user '{username}': {e}. "
                    f"Skipping manager assignment."
                )
            except Exception:
                # Fail silently but log for debugging
                logger.exception(f"Failed to link manager for user '{username}'")
