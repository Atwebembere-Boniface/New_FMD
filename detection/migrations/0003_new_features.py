"""
Migration 0003_new_features — clean version
Dependencies: update '0010_...' to match your actual latest migration filename.
"""

from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        # ← IMPORTANT: change this to your actual latest migration
        ('detection', '0010_detection_annotated_image_detection_result_label_and_more'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [

        # ── Recommendation ────────────────────────────────────────────────
        migrations.CreateModel(
            name='Recommendation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ('urgency', models.CharField(
                    choices=[
                        ('critical', 'Critical — Immediate Action'),
                        ('high', 'High — Act Within 24 Hours'),
                        ('moderate', 'Moderate — Monitor Closely'),
                        ('low', 'Low — Routine Monitoring'),
                    ],
                    default='low', max_length=20)),
                ('summary', models.TextField()),
                ('full_text', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('detection', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='recommendation',
                    to='detection.detection')),
            ],
            options={'ordering': ['-created_at']},
        ),

        # ── DirectMessage (flat inbox — no Conversation wrapper) ──────────
        migrations.CreateModel(
            name='DirectMessage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('body', models.TextField(blank=True)),
                ('image', models.ImageField(blank=True, null=True, upload_to='messages/%Y/%m/%d/')),
                ('is_read', models.BooleanField(default=False)),
                ('sent_at', models.DateTimeField(auto_now_add=True)),
                ('sender', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sent_direct_messages',
                    to='auth.user')),
                ('recipient', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='received_direct_messages',
                    to='auth.user')),
                ('reply_to', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='replies',
                    to='detection.directmessage')),
            ],
            options={'ordering': ['-sent_at']},
        ),

        # ── Appointment (animal_id is nullable — blank=True, null=True) ───
        migrations.CreateModel(
            name='Appointment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('preferred_date', models.DateTimeField()),
                ('reason', models.TextField()),
                ('location', models.CharField(blank=True, max_length=200)),
                # animal_id kept nullable so old rows and new rows both work
                ('animal_id', models.CharField(blank=True, null=True, max_length=100)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending Approval'),
                        ('approved', 'Approved'),
                        ('rejected', 'Rejected'),
                        ('completed', 'Completed'),
                        ('cancelled', 'Cancelled'),
                    ],
                    default='pending', max_length=20)),
                ('vet_notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('farmer', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='appointments_as_farmer',
                    to='auth.user')),
                ('vet', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='appointments_as_vet',
                    to='auth.user')),
            ],
            options={'ordering': ['-preferred_date']},
        ),

        # ── VaccinationRecord ─────────────────────────────────────────────
        migrations.CreateModel(
            name='VaccinationRecord',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('vaccine_name', models.CharField(default='FMD Vaccine', max_length=200)),
                ('batch_number', models.CharField(blank=True, max_length=100)),
                ('date_administered', models.DateField()),
                ('next_due_date', models.DateField(blank=True, null=True)),
                ('administered_by', models.CharField(blank=True, max_length=200)),
                ('notes', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('farmer', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='vaccination_records',
                    to='auth.user')),
            ],
            options={
                'ordering': ['-date_administered'],
                'verbose_name': 'Vaccination Record',
                'verbose_name_plural': 'Vaccination Records',
            },
        ),
    ]
