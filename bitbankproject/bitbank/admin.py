from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from django.utils.translation import ugettext_lazy as _
from .models import User, OrderRelation, BitbankOrder, Alert, Inquiry, Attachment

from django.utils.safestring import mark_safe
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

class MyOrderRelationAdmin(admin.ModelAdmin):
    list_display = ('pk', 'user', 'pair', 'special_order', 'order_1', 'order_2', 'order_3', 'placed_at', 'is_active')
    list_display_links = ('pk',)
class MyBitbankOrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'user', 'pair', 'side', 'order_type', 'price', 'start_amount', 'remaining_amount', 'executed_amount', 'status')
    list_display_links = ('order_id',)
class MyAlertAdmin(admin.ModelAdmin):
    list_display = ('user', 'pair', 'threshold', 'is_active')

class MyInquiryAdmin(admin.ModelAdmin):
    
    list_display = ('user', 'date_initiated', 'subject', 'body', 'email_for_reply', 'show_attachment_1', 'show_attachment_2', 'show_attachment_3')
    def show_attachment_1(self, obj):
        if obj.attachment_1:
            return mark_safe('<img src="{url}" width="{width}" height={height} />'.format(
                url = obj.attachment_1.file.url,
                width = "300px",
                height= "auto",
                )
            )
        else:
            return 'なし'
    def show_attachment_2(self, obj):
        if obj.attachment_2:
            return mark_safe('<img src="{url}" width="{width}" height={height} />'.format(
                url = obj.attachment_2.file.url,
                width = "300px",
                height= "auto",
                )
            )
        else:
            return 'なし'
    def show_attachment_3(self, obj):
        if obj.attachment_2:
            return mark_safe('<img src="{url}" width="{width}" height={height} />'.format(
                url = obj.attachment_3.file.url,
                width = "300px",
                height= "auto",
                )
            )
        else:
            return 'なし'
                   
admin.site.register(User, MyUserAdmin)
admin.site.register(OrderRelation, MyOrderRelationAdmin)
admin.site.register(BitbankOrder, MyBitbankOrderAdmin)

admin.site.register(Alert, MyAlertAdmin)
admin.site.register(Inquiry, MyInquiryAdmin)