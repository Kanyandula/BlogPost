from django.db import migrations
from django.utils.html import strip_tags


def backfill_body_plain(apps, schema_editor):
	BlogPost = apps.get_model('blog', 'BlogPost')
	for post in BlogPost.objects.all().only('id', 'body'):
		post.body_plain = ' '.join(strip_tags(post.body or '').split())
		post.save(update_fields=['body_plain'])


def clear_body_plain(apps, schema_editor):
	BlogPost = apps.get_model('blog', 'BlogPost')
	BlogPost.objects.update(body_plain='')


class Migration(migrations.Migration):

	dependencies = [
		('blog', '0011_blogpost_body_plain'),
	]

	operations = [
		migrations.RunPython(backfill_body_plain, clear_body_plain),
	]
