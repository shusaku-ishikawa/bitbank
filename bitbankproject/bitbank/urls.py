from django.urls import path
from . import views
from django.contrib import admin
from rest_framework.authtoken.views import obtain_auth_token  # <-- Here


app_name = 'bitbank'
admin.site.site_title = 'bitbank' 
admin.site.site_header = 'bitbank' 
admin.site.index_title = 'メニュー'

urlpatterns = [
    path('', views.Login.as_view(), name=''),
    path('login/', views.Login.as_view(), name='login'),
    path('logout/', views.Logout.as_view(), name='logout'),
    path('user_create/', views.UserCreate.as_view(), name='user_create'),
    path('user_create/done', views.UserCreateDone.as_view(), name='user_create_done'),
    path('user_create/complete/<token>/', views.UserCreateComplete.as_view(), name='user_create_complete'),
    path('password_change/', views.PasswordChange.as_view(), name='password_change'),
    path('password_change/done/', views.PasswordChangeDone.as_view(), name='password_change_done'),
    path('password_reset/', views.PasswordReset.as_view(), name='password_reset'),
    path('password_reset/done/', views.PasswordResetDone.as_view(), name='password_reset_done'),
    path('password_reset/confirm/<uidb64>/<token>/', views.PasswordResetConfirm.as_view(), name='password_reset_confirm'),
    path('password_reset/complete/', views.PasswordResetComplete.as_view(), name='password_reset_complete'),
    path('api-token-auth/', obtain_auth_token, name='api_token_auth'),  # <-- And here
    path('ajax_get_user/', views.ajax_get_user, name="ajax_get_user"),
    path('ajax_update_user/', views.ajax_update_user, name="ajax_update_user"),
    path('ajax_get_ticker/', views.ajax_get_ticker, name="ajax_get_ticker"),
    path('ajax_get_assets/', views.ajax_get_assets, name="ajax_get_assets"),
    path('ajax_get_active_orders/', views.ajax_get_active_orders, name="ajax_get_active_orders"),
    path('ajax_get_order_history/', views.ajax_get_order_histroy, name="ajax_get_order_history"),
    path('ajax_get_active_alerts/', views.ajax_get_active_alerts, name="ajax_get_active_alerts"),
    path('ajax_create_alert/', views.ajax_create_alert, name="ajax_create_alert"),
    path('ajax_deactivate_alert/', views.ajax_deactivate_alert, name="ajax_deactivate_alert"),
    path('ajax_cancel_order/', views.ajax_cancel_order, name="ajax_cancel_order"),
    path('ajax_get_notify_if_filled/', views.ajax_get_notify_if_filled, name="ajax_get_notify_if_filled"),
    path('ajax_change_notify_if_filled/', views.ajax_change_notify_if_filled, name="ajax_change_notify_if_filled"),
    path('ajax_create_order/', views.ajax_create_order, name="ajax_create_order"),
    #path('ajax_upload_files/', views.ajax_upload_files, name="ajax_upload_files"),
    path('ajax_post_inquiry/', views.ajax_post_inquiry, name="ajax_post_inquiry"),
    path('order/', views.MainPage.as_view(), name='order'),
]