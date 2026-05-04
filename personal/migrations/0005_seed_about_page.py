from django.db import migrations


ABOUT_BODY = """
<p class="text-lg leading-relaxed">
NyasaBlog is a digital platform dedicated to promoting positive content created by Malawian content creators and influencers. Our aim is to be the most trusted source for Malawian content in the areas of Culture, Entertainment, Entrepreneurship, and many more.
</p>

<div class="bg-surface-container-low p-8 rounded-2xl my-10">
  <h2 class="text-xl font-bold text-primary mb-3">Our Mission</h2>
  <p>To amplify Malawian voices and showcase the best of Malawian creativity, innovation, and culture to the world.</p>
</div>

<h2 class="text-xl font-bold text-primary mb-3">Categories We Cover</h2>
<div class="flex flex-wrap gap-2 mb-8">
  <span class="px-4 py-2 rounded-full bg-surface-container text-on-surface-variant text-sm">Culture</span>
  <span class="px-4 py-2 rounded-full bg-surface-container text-on-surface-variant text-sm">Entertainment</span>
  <span class="px-4 py-2 rounded-full bg-surface-container text-on-surface-variant text-sm">Entrepreneurship</span>
  <span class="px-4 py-2 rounded-full bg-surface-container text-on-surface-variant text-sm">Tourism</span>
  <span class="px-4 py-2 rounded-full bg-surface-container text-on-surface-variant text-sm">Technology</span>
  <span class="px-4 py-2 rounded-full bg-surface-container text-on-surface-variant text-sm">Sports</span>
  <span class="px-4 py-2 rounded-full bg-surface-container text-on-surface-variant text-sm">Lifestyle</span>
  <span class="px-4 py-2 rounded-full bg-surface-container text-on-surface-variant text-sm">Education</span>
  <span class="px-4 py-2 rounded-full bg-surface-container text-on-surface-variant text-sm">Health</span>
  <span class="px-4 py-2 rounded-full bg-surface-container text-on-surface-variant text-sm">Opinion</span>
</div>

<div class="bg-[#0f3d3e] text-white p-8 rounded-2xl">
  <h2 class="text-xl font-bold mb-3">Founded by Ephraim Kanyandula</h2>
  <p>NyasaBlog was created by Ephraim Kanyandula, a Malawian national, with the vision of building a platform that amplifies Malawian voices and showcases the best of Malawian creativity and innovation.</p>
</div>
""".strip()


def seed_about(apps, schema_editor):
	Page = apps.get_model('personal', 'Page')
	Page.objects.update_or_create(
		slug='about',
		defaults={
			'title': 'About NyasaBlog',
			'body': ABOUT_BODY,
			'is_published': True,
		},
	)


def unseed_about(apps, schema_editor):
	Page = apps.get_model('personal', 'Page')
	Page.objects.filter(slug='about').delete()


class Migration(migrations.Migration):

	dependencies = [
		('personal', '0004_page'),
	]

	operations = [
		migrations.RunPython(seed_about, unseed_about),
	]
