from django.db import migrations, models


def grandfather(apps, schema_editor):
    Account = apps.get_model('account', 'Account')
    BlogPost = apps.get_model('blog', 'BlogPost')
    contributor_ids = set(BlogPost.objects.values_list('author_id', flat=True))
    Account.objects.filter(
        models.Q(is_staff=True) | models.Q(is_superuser=True) | models.Q(pk__in=contributor_ids)
    ).update(email_verified=True)


class Migration(migrations.Migration):
    dependencies = [
        ('account', '0005_account_email_verified'),
        ('blog', '0001_initial'),
    ]
    operations = [
        migrations.RunPython(grandfather, migrations.RunPython.noop),
    ]
