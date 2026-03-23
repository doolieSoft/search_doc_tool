from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("search_tool", "0004_indexingstatus_last_ping"),
    ]

    operations = [
        migrations.CreateModel(
            name="BrowseRoot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=200)),
                ("path", models.CharField(max_length=500, unique=True)),
            ],
            options={
                "verbose_name": "Dossier autorisé",
                "ordering": ["label"],
            },
        ),
    ]
