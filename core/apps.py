from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Thin cross-cutting support app.

    Hosts operational endpoints (health checks) and shared base classes. It defines
    no models, so it contributes no migrations.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
