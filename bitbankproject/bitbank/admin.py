from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.utils.translation import ugettext_lazy as _
from .models import User, Order, Alert
# from django.contrib.auth import get_user_model

# User = get_user_model()

class MyUserChangeForm(UserChangeForm):
    class Meta:
        model = User
        fields = '__all__'


class MyUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('email',)


class MyUserAdmin(UserAdmin):
    fieldsets = (
        (None, {'fields': ('full_name', 'remaining_days','email', 'password')}),
        (_('Personal info'), {'fields': ('api_key', 'api_secret_key', 'notify_if_filled', 'email_for_notice')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser')}),
        (_('Important dates'), {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('full_name', 'email', 'password1', 'password2'),
        }),
    )
    form = MyUserChangeForm
    add_form = MyUserCreationForm
    list_display = ('full_name', 'remaining_days', 'email',  'is_active', 'is_staff', 'date_joined',)
    list_filter = ('remaining_days', 'is_staff', 'is_active')
    search_fields = ('email','full_name')

    ordering = ('remaining_days',)

class MyOrderAdmin(admin.ModelAdmin):
    list_display = ('user', 'order_id', 'pair', 'special_order', 'side', 'order_type', 'price', 'start_amount', 'remaining_amount', 'executed_amount', 'status')

class MyAlertAdmin(admin.ModelAdmin):
    list_display = ('user', 'pair', 'threshold', 'is_active')

admin.site.register(User, MyUserAdmin)
admin.site.register(Order, MyOrderAdmin)
admin.site.register(Alert, MyAlertAdmin)