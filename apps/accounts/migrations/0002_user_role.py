from django.db import migrations, models


def promote_existing_admins(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(is_superuser=True).update(role="admin", is_staff=True)
    User.objects.filter(username="mAdmin").update(role="admin", is_staff=True, is_superuser=True)


def demote_existing_admins(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(role="admin").update(role="user")


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[("admin", "Admin"), ("user", "User")],
                default="user",
                max_length=20,
            ),
        ),
        migrations.RunPython(promote_existing_admins, demote_existing_admins),
    ]
