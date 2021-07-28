# Generated by Django 3.2 on 2021-07-28 05:37

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('emp', '0035_alter_shortlistemailstatus_date_created'),
    ]

    operations = [
        migrations.AlterField(
            model_name='company',
            name='city_c',
            field=models.IntegerField(default=None, null=True, verbose_name=''),
        ),
        migrations.AlterField(
            model_name='company',
            name='emp_contact',
            field=models.CharField(blank=True, max_length=17, null=True, validators=[django.core.validators.RegexValidator(message='Invalid.', regex='^\\+?1?\\d{9,15}$')], verbose_name='Phone Number'),
        ),
        migrations.AlterField(
            model_name='company',
            name='state_c',
            field=models.IntegerField(default=None, null=True, verbose_name='State (Company Headquarters)'),
        ),
    ]
