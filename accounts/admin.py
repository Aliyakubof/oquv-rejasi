from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import (
    Department,
    Foydalanuvchi,
    OqituvchiProfil,
    OqituvchiTuri,
    Universitet,
)


@admin.register(Foydalanuvchi)
class FoydalanuvchiAdmin(UserAdmin):
    model = Foydalanuvchi
    ordering = ("telefon",)
    list_display = ("telefon", "first_name", "last_name", "rol", "is_staff")
    search_fields = ("telefon", "first_name", "last_name")
    fieldsets = (
        (None, {"fields": ("telefon", "password")}),
        ("Shaxsiy ma'lumot", {"fields": ("first_name", "last_name")}),
        (
            "Ruxsatlar",
            {
                "fields": (
                    "rol",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "telefon",
                    "first_name",
                    "last_name",
                    "rol",
                    "password1",
                    "password2",
                ),
            },
        ),
    )


@admin.register(Universitet)
class UniversitetAdmin(admin.ModelAdmin):
    list_display = ("rasmiy_nomi",)


@admin.register(OqituvchiTuri)
class OqituvchiTuriAdmin(admin.ModelAdmin):
    list_display = ("nomi", "min_soat")


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ("nomi", "mudir")
    list_select_related = ("mudir__foydalanuvchi",)


@admin.register(OqituvchiProfil)
class OqituvchiProfilAdmin(admin.ModelAdmin):
    list_display = ("foydalanuvchi", "kafedra", "turi")
    list_filter = ("kafedra", "turi")
    list_select_related = ("foydalanuvchi", "kafedra", "turi")
    # Required for autocomplete_fields pointing here (plans.Yuklama.oqituvchi).
    search_fields = (
        "foydalanuvchi__first_name",
        "foydalanuvchi__last_name",
        "foydalanuvchi__telefon",
    )
