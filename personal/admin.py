from django.contrib import admin

from personal.models import AboutPage, Subscriber


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
	list_display = ('email', 'confirmed', 'created_at')
	list_filter = ('confirmed',)
	search_fields = ('email',)
	actions = ['export_emails']

	@admin.action(description="Export selected emails")
	def export_emails(self, request, queryset):
		from django.http import HttpResponse
		emails = "\n".join(queryset.values_list('email', flat=True))
		response = HttpResponse(emails, content_type='text/plain')
		response['Content-Disposition'] = 'attachment; filename="subscribers.txt"'
		return response


@admin.register(AboutPage)
class AboutPageAdmin(admin.ModelAdmin):
	"""Singleton admin: hide the changelist 'Add' button so only one row exists."""

	readonly_fields = ('updated_at',)
	fieldsets = (
		(None, {'fields': ('is_published',)}),
		('Intro', {'fields': ('intro',)}),
		('Mission section', {'fields': ('mission_title', 'mission_body')}),
		('Categories section', {'fields': ('categories_heading', 'categories')}),
		('Founder section', {'fields': ('founder_title', 'founder_body')}),
		('Metadata', {'fields': ('updated_at',)}),
	)

	def has_add_permission(self, request):
		# Allow add only if no instance exists yet.
		return not AboutPage.objects.exists()

	def has_delete_permission(self, request, obj=None):
		return False
