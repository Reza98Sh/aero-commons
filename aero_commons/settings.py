"""
Default settings for the custom_users app.
These can be overridden in the main project's settings.py
"""
from django.conf import settings

# LDAP Configuration defaults
CUSTOM_USERS_LDAP_HOST = getattr(settings, "LDAP_HOST", "localhost")
CUSTOM_USERS_LDAP_DOMAIN = getattr(settings, "LDAP_DOMAIN", "DOMAIN")
CUSTOM_USERS_LDAP_USE_SSL = getattr(settings, "LDAP_USE_SSL", False)

# Email domain for auto-generated emails
CUSTOM_USERS_EMAIL_DOMAIN = getattr(settings, "CUSTOM_USERS_EMAIL_DOMAIN", "example.com")


def get_setting(name, default=None):
    """
    Helper function to retrieve settings with fallback to defaults.
    
    Args:
        name: The setting name to retrieve
        default: Default value if setting doesn't exist
        
    Returns:
        The setting value or default
    """
    return getattr(settings, name, default)
