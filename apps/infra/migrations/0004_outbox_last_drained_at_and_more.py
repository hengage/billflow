from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('infra', '0003_outbox_updated_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='outbox',
            name='last_drained_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name='outbox',
            index=models.Index(fields=['status', 'last_drained_at'], name='infra_outbo_status_6da22d_idx'),
        ),
    ]
