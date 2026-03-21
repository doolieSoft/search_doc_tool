from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("search_tool", "0002_indexingstatus"),
    ]

    operations = [
        migrations.CreateModel(
            name="FavoriteGroup",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="favorite_groups", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.AlterUniqueTogether(
            name="favoritegroup",
            unique_together={("user", "name")},
        ),
        migrations.AddField(
            model_name="favorite",
            name="group",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="favorites",
                to="search_tool.favoritegroup",
            ),
        ),
    ]
