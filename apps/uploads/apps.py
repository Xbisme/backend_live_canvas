from django.apps import AppConfig


class UploadsConfig(AppConfig):
    """Uploads domain — presigned upload, transcode pipeline, admin CRUD.

    Model-less shell in BE-002; the upload pipeline lands in BE-004.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.uploads"
