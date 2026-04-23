import re
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _


class UppercasePasswordValidator:
    def validate(self, password, user=None):
        if not re.search(r"[A-ZА-ЯЁ]", password or ""):
            raise ValidationError(_("Пароль должен содержать минимум 1 заглавную букву."), code="password_no_upper")

    def get_help_text(self):
        return _("Пароль должен содержать минимум 1 заглавную букву.")


class SpecialCharPasswordValidator:
    def validate(self, password, user=None):
        if not re.search(r"[^A-Za-zА-Яа-яЁё0-9]", password or ""):
            raise ValidationError(_("Пароль должен содержать минимум 1 спецсимвол."), code="password_no_special")

    def get_help_text(self):
        return _("Пароль должен содержать минимум 1 спецсимвол.")
