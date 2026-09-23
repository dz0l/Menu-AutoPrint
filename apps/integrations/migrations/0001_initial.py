
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='IntegrationOperation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('request_id', models.CharField(db_index=True, max_length=64, unique=True)),
                ('scope', models.CharField(default='default', max_length=64)),
                ('idempotency_key', models.CharField(max_length=128)),
                ('kind', models.CharField(choices=[('create_dish', 'create_dish'), ('pdf', 'pdf')], max_length=32)),
                ('payload_hash', models.CharField(max_length=64)),
                ('status', models.CharField(choices=[('pending', 'pending'), ('succeeded', 'succeeded'), ('failed', 'failed')], default='pending', max_length=16)),
                ('result_json', models.JSONField(blank=True, default=dict)),
                ('result_path', models.CharField(blank=True, max_length=512)),
                ('error_code', models.CharField(blank=True, max_length=64)),
                ('error_message', models.TextField(blank=True)),
                ('http_status', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('expires_at', models.DateTimeField(db_index=True)),
            ],
            options={
                'indexes': [models.Index(fields=['expires_at'], name='integration_expires_a54365_idx')],
                'constraints': [models.UniqueConstraint(fields=('scope', 'kind', 'idempotency_key'), name='uniq_integration_idempotency')],
            },
        ),
    ]
