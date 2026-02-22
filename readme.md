# Aero Commons – Django Active Directory Integration

Aero Commons is a Django installable application that provides **Active Directory (LDAP) authentication and user synchronization**.
It allows Django projects to authenticate users against an **Active Directory domain** and automatically sync user accounts.

## Installation

Install the package directly from the Git repository using `pip`:

```bash
pip install git+http://git.mapnaaero.com/scm/aut/aero-commons.git
```

## Django Configuration

### 1. Add Authentication Backends

Update your `settings.py` to include the LDAP authentication backend:

```python
AUTHENTICATION_BACKENDS = [
    'aero_commons.authentication.LDAPBackend',
    'django.contrib.auth.backends.ModelBackend',
]
```

---

### 2. Set Custom User Model

This package uses a custom user model.
Make sure this is set **before running migrations**:

```python
AUTH_USER_MODEL = 'commons.CustomUser'
```

---

### 3. Register the App

Add the application to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...
    'aero_commons.apps.AeroCommonsConfig',
]
```

---

## LDAP / Active Directory Settings

Configure the following settings in `settings.py`:

```python
LDAP_HOST = 'Srv-AeroADS1.Mapnaaero.com'
LDAP_DOMAIN = 'MAPNAAERO'

LDAP_ADMIN_USER = os.getenv('LDAP_ADMIN_USER')
LDAP_ADMIN_PASSWORD = os.getenv('LDAP_ADMIN_PASSWORD')

LDAP_BASE_DN = 'OU=Aero Organization,DC=Mapnaaero,DC=com'
LDAP_INACTIVE_USERS_DN = 'OU=Useless Objects,OU=Aero Organization Other Users & Groups,DC=Mapnaaero,DC=com'
```

### Environment Variables

For security reasons, LDAP admin credentials **must be stored as environment variables**:

```bash
export LDAP_ADMIN_USER=your_admin_username
export LDAP_ADMIN_PASSWORD=your_admin_password
```
