from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from account.models import Account, UserProfile


class AccountAdmin(UserAdmin):
	list_display = ('email','username','date_joined', 'last_login', 'is_admin','is_staff')
	search_fields = ('email','username',)
	readonly_fields=('date_joined', 'last_login')

	filter_horizontal = ()
	list_filter = ()
	fieldsets = ()


class UserProfileInline(admin.StackedInline):
	model = UserProfile
	can_delete = False


class AccountAdminWithProfile(AccountAdmin):
	inlines = [UserProfileInline]


admin.site.register(Account, AccountAdminWithProfile)
admin.site.register(UserProfile)
