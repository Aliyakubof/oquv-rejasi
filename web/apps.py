from django.apps import AppConfig


class WebConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "web"

    def ready(self) -> None:
        from web.views.jonli import signallarni_ulash

        signallarni_ulash()
