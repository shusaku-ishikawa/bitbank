from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.utils.translation import ugettext_lazy as _
from .models import User, Order
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
        (None, {'fields': ('full_name', 'email', 'password')}),
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
    list_display = ('email', 'full_name', 'is_active', 'is_staff')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups')
    search_fields = ('email',)

    ordering = ('email',)

class MyOrderAdmin(admin.ModelAdmin):
    list_display = ('user', 'order_id', 'pair', 'special_order', 'side', 'order_type', 'price', 'start_amount', 'remaining_amount', 'executed_amount', 'status')

admin.site.register(User, MyUserAdmin)
admin.site.register(Order, MyOrderAdmin)