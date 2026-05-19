from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0004_reminderpolicy'),
    ]

    operations = [
        migrations.AddField(
            model_name='reminderpolicy',
            name='email_enabled',
            field=models.BooleanField(
                default=False,
                help_text='Also send reminders and receipts by email to guardians.',
            ),
        ),
    ]
