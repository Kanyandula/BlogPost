from django.db import migrations, models


DEFAULT_INTRO = (
	"NyasaBlog is a digital platform dedicated to promoting positive content "
	"created by Malawian content creators and influencers. Our aim is to be "
	"the most trusted source for Malawian content in the areas of Culture, "
	"Entertainment, Entrepreneurship, and many more."
)

DEFAULT_MISSION_BODY = (
	"To amplify Malawian voices and showcase the best of Malawian creativity, "
	"innovation, and culture to the world."
)

DEFAULT_CATEGORIES = (
	"Culture, Entertainment, Entrepreneurship, Tourism, Technology, "
	"Sports, Lifestyle, Education, Health, Opinion"
)

DEFAULT_FOUNDER_BODY = (
	"NyasaBlog was created by Ephraim Kanyandula, a Malawian national, with "
	"the vision of building a platform that amplifies Malawian voices and "
	"showcases the best of Malawian creativity and innovation."
)


def seed_about(apps, schema_editor):
	AboutPage = apps.get_model('personal', 'AboutPage')
	if not AboutPage.objects.exists():
		AboutPage.objects.create(
			intro=DEFAULT_INTRO,
			mission_title='Our Mission',
			mission_body=DEFAULT_MISSION_BODY,
			categories_heading='Categories We Cover',
			categories=DEFAULT_CATEGORIES,
			founder_title='Founded by Ephraim Kanyandula',
			founder_body=DEFAULT_FOUNDER_BODY,
			is_published=True,
		)


def unseed_about(apps, schema_editor):
	AboutPage = apps.get_model('personal', 'AboutPage')
	AboutPage.objects.all().delete()


class Migration(migrations.Migration):

	dependencies = [
		('personal', '0005_seed_about_page'),
	]

	operations = [
		migrations.CreateModel(
			name='AboutPage',
			fields=[
				('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
				('intro', models.TextField(help_text='The opening paragraph beneath the page title.')),
				('mission_title', models.CharField(default='Our Mission', max_length=80)),
				('mission_body', models.TextField()),
				('categories_heading', models.CharField(default='Categories We Cover', max_length=80)),
				('categories', models.TextField(help_text='Comma-separated list of category labels (e.g. "Culture, Entertainment, Tourism").')),
				('founder_title', models.CharField(default='Founded by Ephraim Kanyandula', max_length=120)),
				('founder_body', models.TextField()),
				('is_published', models.BooleanField(default=True)),
				('updated_at', models.DateTimeField(auto_now=True)),
			],
			options={
				'verbose_name': 'About page',
				'verbose_name_plural': 'About page',
			},
		),
		migrations.RunPython(seed_about, unseed_about),
		migrations.DeleteModel(
			name='Page',
		),
	]
