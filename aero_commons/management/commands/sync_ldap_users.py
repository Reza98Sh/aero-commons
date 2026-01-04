import uuid

from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.db import transaction
from django.conf import settings
from ldap3 import Server, Connection, ALL, SUBTREE

from users.models import CustomUser, UserInfo, Position, Department


class Command(BaseCommand):
    help = "Synchronize users from LDAP to database with Pagination"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run without making changes to database",
        )

    def get_ldap_connection(self):
        """
        Establish and return an LDAP connection using settings.
        """
        server = Server(settings.LDAP_HOST, get_info=ALL)
        conn = Connection(
            server,
            user=settings.LDAP_ADMIN_USER,
            password=settings.LDAP_ADMIN_PASSWORD,
            auto_bind=True,
        )
        return conn
    def fetch_ldap_entries(self, conn):
        """
        Perform LDAP search with pagination logic (Paged Results).
        """
        entries = []
        page_size = 1000
        search_filter = "(objectCategory=Person)"
        
        # Define specific attributes to fetch including thumbnailPhoto
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
        
        # Initial search with paged_size
        conn.search(
            search_base=settings.LDAP_BASE_DN,
            search_filter=search_filter,
            search_scope=SUBTREE,
            attributes=attributes,  # Use specific attributes instead of "*"
            paged_size=page_size,
        )
        
        # Add first batch of entries
        if conn.entries:
            entries.extend(conn.entries)

        # Loop while the server returns a pagination cookie
        controls = conn.result.get("controls", {})
        while "1.2.840.113556.1.4.319" in controls:
            cookie = controls["1.2.840.113556.1.4.319"]["value"]["cookie"]
            
            if not cookie:
                break
            
            self.stdout.write(f"Fetching next page... (Total fetched so far: {len(entries)})")

            conn.search(
                search_base=settings.LDAP_BASE_DN,
                search_filter=search_filter,
                search_scope=SUBTREE,
                attributes=attributes,  # Use same attributes list
                paged_size=page_size,
                paged_cookie=cookie,
            )
            
            if conn.entries:
                entries.extend(conn.entries)
            
            controls = conn.result.get("controls", {})

        self.stdout.write(self.style.SUCCESS(f"Total objects fetched from LDAP: {len(entries)}"))
        return entries
    

    def extract_entry_data(self, entry):
        """
        Extract username, user_data, info_data, position_title, department, and thumbnail.
        Returns None if entry has no uid.
        """
        if not hasattr(entry, "sAMAccountName"):
            return None

        username = str(entry.sAMAccountName)
        
        if username == "Ghasemi.Mohammad2":
            print(username)

        ldap_uuid = None
        if hasattr(entry, "objectGUID") and entry.objectGUID:
            try:
                ldap_uuid = uuid.UUID(str(entry.objectGUID))
            except ValueError:
                pass

        # Prepare CustomUser data
        user_data = {
            "email": (
                str(entry.mail)
                if hasattr(entry, "mail") and entry.mail
                else f"{username}@mapnaaero.com"
            ),
            "first_name": str(entry.givenName) if hasattr(entry, "givenName") else "",
            "last_name": str(entry.sn) if hasattr(entry, "sn") else "",
            "use_ldap": True,
            "ldap_id": ldap_uuid,
        }

        # Extract thumbnailPhoto - it comes as raw bytes from LDAP
        thumbnail_data = None
        if hasattr(entry, "thumbnailPhoto") and entry.thumbnailPhoto:
            try:
                # thumbnailPhoto is typically returned as raw bytes
                raw_photo = entry.thumbnailPhoto.value
                if raw_photo:
                    thumbnail_data = raw_photo
            except Exception as e:
                self.stdout.write(f"Error extracting thumbnail for {username}: {e}")

        # Prepare UserInfo data
        info_data = {
            "phone": (
                str(entry.telephoneNumber) if hasattr(entry, "telephoneNumber") else ""
            ),
            "personnel_code": (
                str(entry.postalCode) if hasattr(entry, "postalCode") else None
            ),
        }

        title = str(entry.title) if hasattr(entry, "title") else None
        department = str(entry.department) if hasattr(entry, "department") else None
        manager_dn = str(entry.manager) if hasattr(entry, "manager") else None
        cn = str(entry.cn) if hasattr(entry, "cn") else None

        return {
            "username": username,
            "user_data": user_data,
            "cn": cn,
            "info_data": info_data,
            "position_title": title,
            "department_name": department,
            "manager_dn": manager_dn,
            "thumbnail_data": thumbnail_data,  # Add thumbnail data
        }
    def get_or_create_department(self, name):
        """
        Retrieve or create a Department by its name.
        """
        if not name:
            return None

        department, _ = Department.objects.get_or_create(
            name=name,
        )
        return department

    def get_or_create_position(self, title: str, department_obj):
        """
        Retrieve or create a Position by its title and link to Department.
        """
        position, _ = Position.objects.get_or_create(
            title_en=title, defaults={"department": department_obj}
        )

        if position.department != department_obj:
            position.department = department_obj
            position.save()

        return position

    def sync_record(self, record, dry_run=False):
        """
        Sync a single user record to the database including thumbnail photo.
        """
        username = record["username"]
        user_data = record["user_data"]
        info_data = record["info_data"]
        position_title = record["position_title"]
        department_name = record["department_name"]
        cn = record["cn"]
        thumbnail_data = record.get("thumbnail_data")

        if dry_run:
            self.stdout.write(f"[DRY RUN] Would process user: {username}")
            return None, None

        with transaction.atomic():
            user, created = CustomUser.objects.update_or_create(
                username=username,
                defaults=user_data,
            )
            user.cn = cn
            user.save()

            position = None
            if position_title:
                dept_obj = self.get_or_create_department(department_name)
                position = self.get_or_create_position(position_title, dept_obj)

                if user.position != position:
                    user.position = position
                    user.save()

            user_info, info_created = UserInfo.objects.update_or_create(
                user=user, defaults=info_data
            )

            # Save thumbnail photo if available
            if thumbnail_data:
                try:
                    # Create a ContentFile from the raw bytes
                    # The filename will be username.jpg (most LDAP photos are JPEG)
                    photo_file = ContentFile(thumbnail_data, name=f"{username}.jpg")
                    
                    # Delete old thumbnail if exists to avoid orphaned files
                    if user_info.thumbnail:
                        user_info.thumbnail.delete(save=False)
                    
                    user_info.thumbnail.save(f"{username}.jpg", photo_file, save=True)
                    self.stdout.write(f"Saved thumbnail for {username}")
                except Exception as e:
                    self.stderr.write(f"Error saving thumbnail for {username}: {e}")

        return created, user

    def link_managers(self, user_manager_map, dry_run=False):
        """
        Second pass: Link users to their direct managers.
        """
        self.stdout.write("Linking managers...")
        count = 0

        for username, manager_dn in user_manager_map.items():
            if not manager_dn:
                continue

            try:
                # Extract CN like "CN=Sharafi.Reza,OU=..." -> "Sharafi.Reza"
                manager_cn = manager_dn.split(",")[0].split("=")[1]
            except IndexError:
                continue
            
            # # Assuming username format in DB matches this replacement
            # manager_cn = manager_cn.replace(" ", ".")
            
            if dry_run:
                self.stdout.write(f"[DRY RUN] Would link {username} to manager {manager_cn}")
                continue

            try:
                employee = CustomUser.objects.get(username=username)
                
                # Using iexact for case-insensitive match
                manager_user = CustomUser.objects.filter(
                    cn__iexact=manager_cn
                ).first()

                if manager_user and employee.id != manager_user.id:
                    if employee.direct_manager != manager_user:
                        employee.direct_manager = manager_user
                        employee.save()
                        count += 1
                        self.stdout.write(f"Linked {username} to manager {manager_cn}")
                else:
                    self.stdout.write(f"Manager not found in DB: {manager_cn}") 
                    pass

            except CustomUser.DoesNotExist:
                pass

        self.stdout.write(self.style.SUCCESS(f"Linked {count} managers."))


    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        conn = None
        try:
            self.stdout.write("Connecting to LDAP...")
            conn = self.get_ldap_connection()
            
            self.stdout.write("Fetching LDAP entries with pagination...")
            entries = self.fetch_ldap_entries(conn)
            
            self.stdout.write(f"Filtering {len(entries)} entries...")
            self.stdout.write(f"Processing {len(entries)} valid entries...")

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"LDAP Error: {e}"))
            if conn:
                conn.unbind()
            return

        created_count = 0
        updated_count = 0
        user_manager_map = {}

        # Pass 1: Create/Update Users
        for entry in entries:
            try:
                record = self.extract_entry_data(entry)
                if not record:
                    continue

                user_manager_map[record["username"]] = record["manager_dn"]

                result, _ = self.sync_record(record, dry_run)

                if result is True:
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f"Created: {record['username']}"))
                elif result is False:
                    updated_count += 1
                
            except Exception as e:
                # Fallback to string representation if attribute access fails in error msg
                self.stderr.write(self.style.ERROR(f"Error processing entry: {e}"))

        # Unbind connection after fetching and processing basic data is done
        if conn:
            conn.unbind()

        # Pass 2: Link Managers
        self.link_managers(user_manager_map, dry_run)

        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run completed."))
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Sync completed! Created: {created_count}, Updated: {updated_count}"
                )
            )
