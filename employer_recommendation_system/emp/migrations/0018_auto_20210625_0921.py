# Generated by Django 3.2 on 2021-06-25 09:21

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('emp', '0017_auto_20210624_0735'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='student',
            name='experience',
        ),
        migrations.AlterField(
            model_name='education',
            name='gpa',
            field=models.CharField(max_length=10, null=True),
        ),
    ]