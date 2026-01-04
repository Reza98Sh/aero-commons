from django.apps import AppConfig


class AeroCommonsConfig(AppConfig):
    """
    Application configuration for the common app.
    """
    
    default_auto_field = "django.db.models.BigAutoField"
    name = "aero_commons"
    label = "commons"
    
        
    def ready(self):
        """
        Perform initialization tasks when the app is ready.
        Import signals or perform other setup tasks here.
        """
        pass