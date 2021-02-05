# Generated by Django 3.1.6 on 2021-02-05 10:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("authentik_sources_ldap", "0009_auto_20210204_1834"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ldapsource",
            name="group_object_filter",
            field=models.TextField(
                default="(objectClass=group)",
                help_text="Consider Objects matching this filter to be Groups.",
            ),
        ),
        migrations.AlterField(
            model_name="ldapsource",
            name="user_object_filter",
            field=models.TextField(
                default="(objectClass=person)",
                help_text="Consider Objects matching this filter to be Users.",
            ),
        ),
    ]
