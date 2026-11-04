from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils import timezone

from accounts.phone import normalize_phone, validate_uzbek_phone


class Rol(models.TextChoices):
    SUPERADMIN = "SUPERADMIN", "Superadmin"
    OFFICE_ADMIN = "OFFICE_ADMIN", "Ofis admin"
    DEPARTMENT_ADMIN = "DEPARTMENT_ADMIN", "Kafedra mudiri"
    TEACHER = "TEACHER", "O'qituvchi"


class FoydalanuvchiManager(BaseUserManager):
    def _create_user(
        self, telefon: str, password: str | None, **extra_fields: object
    ) -> "Foydalanuvchi":
        telefon = normalize_phone(telefon)
        user = self.model(telefon=telefon, **extra_fields)
        user.set_password(password)
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(
        self, telefon: str, password: str | None = None, **extra_fields: object
    ) -> "Foydalanuvchi":
        extra_fields.setdefault("rol", Rol.TEACHER)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(telefon, password, **extra_fields)

    def create_superuser(
        self, telefon: str, password: str | None = None, **extra_fields: object
    ) -> "Foydalanuvchi":
        extra_fields["rol"] = Rol.SUPERADMIN
        extra_fields["is_staff"] = True
        extra_fields["is_superuser"] = True
        return self._create_user(telefon, password, **extra_fields)


class Foydalanuvchi(AbstractBaseUser, PermissionsMixin):
    """Custom user: logs in with phone number, not username/email."""

    telefon = models.CharField(
        max_length=13,
        unique=True,
        db_index=True,
        validators=[validate_uzbek_phone],
        help_text="Format: +998912681260",
    )
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    rol = models.CharField(max_length=20, choices=Rol.choices)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = FoydalanuvchiManager()

    USERNAME_FIELD = "telefon"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    def __str__(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.telefon

    def get_full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self) -> str:
        return self.first_name

    @property
    def rasmiy_qisqa_ism(self) -> str:
        """'Husainov I.' — surname + given-name initial, for official documents."""
        return (
            f"{self.last_name} {self.first_name[0]}."
            if self.first_name
            else self.last_name
        )

    @property
    def is_superadmin(self) -> bool:
        return self.rol == Rol.SUPERADMIN

    @property
    def is_office_admin(self) -> bool:
        return self.rol == Rol.OFFICE_ADMIN

    @property
    def is_department_admin(self) -> bool:
        return self.rol == Rol.DEPARTMENT_ADMIN

    @property
    def is_teacher(self) -> bool:
        return self.rol == Rol.TEACHER


class OqituvchiTuri(models.Model):
    """Dynamic teacher position type (e.g. Professor, Katta o'qituvchi)."""

    nomi = models.CharField(max_length=100, unique=True)
    min_soat = models.PositiveIntegerField(help_text="Yuklama: minimal soat")

    class Meta:
        ordering = ["nomi"]

    def __str__(self) -> str:
        return self.nomi


class Universitet(models.Model):
    """Institution-wide info. Expected to hold exactly one row."""

    rasmiy_nomi = models.CharField(max_length=255)

    class Meta:
        verbose_name = "Universitet"
        verbose_name_plural = "Universitet"

    def __str__(self) -> str:
        return self.rasmiy_nomi


class Department(models.Model):
    """Kafedra."""

    nomi = models.CharField(max_length=200, unique=True)
    fakultet = models.CharField(max_length=200, blank=True)
    mudir = models.OneToOneField(
        "OqituvchiProfil",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="boshqarayotgan_kafedra",
    )

    class Meta:
        ordering = ["nomi"]

    def __str__(self) -> str:
        return self.nomi


class OqituvchiProfilQuerySet(models.QuerySet):
    """Department-scoped and pre-joined teacher queries."""

    def kafedrada(self, kafedra: Department | int) -> "OqituvchiProfilQuerySet":
        return self.filter(kafedra=kafedra)

    def bilan_foydalanuvchi(self) -> "OqituvchiProfilQuerySet":
        return self.select_related("foydalanuvchi")

    def toliq(self) -> "OqituvchiProfilQuerySet":
        return self.select_related("foydalanuvchi", "kafedra", "turi")


class OqituvchiProfil(models.Model):
    """Teacher-specific data, kept off the lean Foydalanuvchi model."""

    foydalanuvchi = models.OneToOneField(
        Foydalanuvchi, on_delete=models.CASCADE, related_name="oqituvchi_profil"
    )
    kafedra = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="oqituvchilar"
    )
    turi = models.ForeignKey(
        OqituvchiTuri, on_delete=models.PROTECT, related_name="oqituvchilar"
    )

    objects = OqituvchiProfilQuerySet.as_manager()

    def __str__(self) -> str:
        return str(self.foydalanuvchi)
