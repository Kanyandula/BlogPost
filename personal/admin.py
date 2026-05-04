from django.contrib import admin

from personal.models import Page, Subscriber


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


@admin.register(Page)
class PageAdmin(admin.ModelAdmin):
	list_display = ('slug', 'title', 'is_published', 'updated_at')
	list_filter = ('is_published',)
	search_fields = ('slug', 'title')
	readonly_fields = ('updated_at',)
	fields = ('slug', 'title', 'is_published', 'body', 'updated_at')
