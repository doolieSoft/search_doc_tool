from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("search_tool", "0003_favoritegroup_favorite_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="indexingstatus",
            name="last_ping",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
