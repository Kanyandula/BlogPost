import html

from django.db import migrations
from django.utils.html import strip_tags


def rebackfill_with_unescape(apps, schema_editor):
	"""Re-populate body_plain decoding HTML entities (&amp; → &).

	0012 backfilled with strip_tags only, leaving entities literal. This pass
	matches the new pre_save logic so existing rows stay aligned with future
	saves.
	"""
	BlogPost = apps.get_model('blog', 'BlogPost')
	for post in BlogPost.objects.all().only('id', 'body'):
		post.body_plain = ' '.join(html.unescape(strip_tags(post.body or '')).split())
		post.save(update_fields=['body_plain'])


def noop(apps, schema_editor):
	# Reverse is a no-op — the previous migration's value is still a valid
	# (just less-decoded) representation of the body.
	pass


class Migration(migrations.Migration):

	dependencies = [
		('blog', '0012_backfill_body_plain'),
	]

	operations = [
		migrations.RunPython(rebackfill_with_unescape, noop),
	]
