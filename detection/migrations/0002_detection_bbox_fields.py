"""
Migration: Add annotated_image, result_label, bounding_boxes to Detection.
Update result choices to two options (fmd / healthy).

Run with:
    python manage.py migrate detection
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        # Replace 'XXXX_previous' with the name of your last migration file
        ('detection', '0001_initial'),
    ]

    operations = [
        # 1. Add annotated image field
        migrations.AddField(
            model_name='detection',
            name='annotated_image',
            field=models.ImageField(
                blank=True, null=True,
                upload_to='annotated_images/%Y/%m/%d/'
            ),
        ),
        # 2. Add human-readable result label field
        migrations.AddField(
            model_name='detection',
            name='result_label',
            field=models.CharField(blank=True, default='', max_length=100),
        ),
        # 3. Add bounding_boxes JSON field
        migrations.AddField(
            model_name='detection',
            name='bounding_boxes',
            field=models.JSONField(blank=True, default=list),
        ),
        # 4. Update result choices (old 'not_cow' rows become 'healthy')
        migrations.RunSQL(
            sql="UPDATE detection_detection SET result = 'healthy' WHERE result = 'not_cow';",
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.AlterField(
            model_name='detection',
            name='result',
            field=models.CharField(
                blank=True, null=True,
                max_length=20,
                choices=[
                    ('healthy', 'Foot and mouth disease not detected'),
                    ('fmd', 'Foot and mouth disease detected'),
                ],
            ),
        ),
    ]
