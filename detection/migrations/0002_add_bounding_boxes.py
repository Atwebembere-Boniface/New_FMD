from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('detection', '0001_initial'),
    ]
    operations = [
        migrations.AddField(
            model_name='detection',
            name='bounding_boxes',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
