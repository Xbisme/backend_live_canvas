from django.apps import AppConfig


class WallpapersConfig(AppConfig):
    """Content domain — Category, Tag, Wallpaper, Collection + public read API.

    Model-less shell in BE-002; business models land in BE-003.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.wallpapers"
