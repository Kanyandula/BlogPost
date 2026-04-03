from django.contrib import admin

from personal.models import Subscriber


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
