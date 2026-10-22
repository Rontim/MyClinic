from django import forms
from django.contrib import admin
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from accounts.models import Role, User

from .models import Doctor, WorkingHours


class WorkingHoursInline(admin.TabularInline):
    model = WorkingHours
    extra = 1


class DoctorCreateForm(forms.ModelForm):
    """Staff provision a doctor in one step: login (email + password) and profile."""

    email = forms.EmailField(help_text="The doctor logs in with this email.")
    password = forms.CharField(widget=forms.PasswordInput, strip=False)

    class Meta:
        model = Doctor
        fields = ("full_name", "specialty", "is_active")

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"])
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("A user with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        if password:
            try:
                validate_password(password, User(
                    email=cleaned.get("email", "")))
            except ValidationError as exc:
                self.add_error("password", exc)
        return cleaned


class DoctorChangeForm(forms.ModelForm):
    new_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput,
        strip=False,
        help_text="Leave blank to keep the current password.",
    )

    class Meta:
        model = Doctor
        fields = ("full_name", "specialty", "is_active")

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("new_password")
        if password:
            try:
                validate_password(password, self.instance.user)
            except ValidationError as exc:
                self.add_error("new_password", exc)
        return cleaned


@admin.register(Doctor)
class DoctorAdmin(admin.ModelAdmin):
    list_display = ("full_name", "specialty", "login_email", "is_active")
    list_filter = ("is_active", "specialty")
    search_fields = ("full_name", "user__email")
    list_select_related = ("user",)
    readonly_fields = ("login_email",)
    inlines = [WorkingHoursInline]

    @admin.display(description="Login email")
    def login_email(self, obj):
        return obj.user.email

    def get_form(self, request, obj=None, **kwargs):
        kwargs["form"] = DoctorChangeForm if obj else DoctorCreateForm
        return super().get_form(request, obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return [(None, {"fields": ("email", "password", "full_name", "specialty", "is_active")})]
        return [(None, {"fields": ("login_email", "new_password", "full_name", "specialty", "is_active")})]

    def save_model(self, request, obj, form, change):
        # The admin change view runs in one transaction, so a failure here rolls back the user too.
        if change:
            new_password = form.cleaned_data.get("new_password")
            if new_password:
                obj.user.set_password(new_password)
                obj.user.save(update_fields=["password"])
        else:
            obj.user = User.objects.create_user(
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
                role=Role.DOCTOR,
            )
        super().save_model(request, obj, form, change)
