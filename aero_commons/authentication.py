"""
LDAP Authentication Backend for Django.
Provides NTLM-based LDAP authentication support.
"""
import logging

from django.conf import settings
from django.contrib import messages
from ldap3 import Server, Connection, ALL, NTLM
from django.contrib.auth import get_user_model

# Get the logger for this module
logger = logging.getLogger(__name__)

# Get the custom user model
User = get_user_model()


class LDAPBackend:
    """
    Custom authentication backend that authenticates users against an LDAP server
    using NTLM authentication.
    
    Required settings in your project's settings.py:
        - LDAP_HOST: The hostname or IP of the LDAP server
        - LDAP_DOMAIN: The domain name for NTLM authentication
    """
    
    def authenticate(self, request, username=None, password=None):
        """
        Authenticate a user against the LDAP server.
        
        Args:
            request: The HTTP request object
            username: The username to authenticate
            password: The password to authenticate
            
        Returns:
            User object if authentication succeeds, None otherwise
        """
        # Validate input parameters
        if not username or not password:
            return None
            
        # Normalize username to lowercase
        username = username.lower()
        
        # Build NTLM username format: DOMAIN\username
        ntlm_username = f"{settings.LDAP_DOMAIN}\\{username}"
        
        # Get LDAP settings with defaults
        ldap_host = getattr(settings, "LDAP_HOST", "localhost")
        ldap_use_ssl = getattr(settings, "LDAP_USE_SSL", False)
        
        # Create LDAP server connection
        server = Server(
            f"ldap://{ldap_host}", 
            use_ssl=ldap_use_ssl, 
            get_info=ALL
        )
        
        try:
            # Attempt LDAP connection with NTLM authentication
            with Connection(
                server, 
                user=ntlm_username, 
                password=password, 
                authentication=NTLM
            ) as conn:
                if conn.bind():
                    logger.info(f"LDAP authentication successful for user: {username}")
                    
                    # Try to get existing user from database
                    try:
                        user = User.objects.get(username=username)
                        return user
                    except User.DoesNotExist:
                        logger.warning(
                            f"User {username} authenticated via LDAP but "
                            f"does not exist in database"
                        )
                        # Optionally create user automatically:
                        # return self._create_user_from_ldap(username, conn)
                        return None
                else:
                    logger.warning(f"LDAP authentication failed for user: {username}")
                    if request:
                        messages.error(request, "Invalid username or password.")
                    return None
                    
        except Exception as e:
            logger.error(f"LDAP authentication error for user {username}: {str(e)}")
            return None
    
    def get_user(self, user_id):
        """
        Retrieve a user by their primary key.
        
        Args:
            user_id: The primary key of the user
            
        Returns:
            User object if found, None otherwise
        """
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
    
    def _create_user_from_ldap(self, username, ldap_connection):
        """
        Create a new user from LDAP data.
        Override this method to customize user creation.
        
        Args:
            username: The username for the new user
            ldap_connection: Active LDAP connection for fetching user data
            
        Returns:
            Newly created User object
        """
        user = User.objects.create(
            username=username,
            use_ldap=True,
        )
        logger.info(f"Created new user from LDAP: {username}")
        return user
