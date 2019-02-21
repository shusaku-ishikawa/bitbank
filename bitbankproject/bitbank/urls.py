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
    
    path('user/', views.ajax_user, name="ajax_user"),
    path('notify_if_filled/', views.ajax_notify_if_filled, name="ajax_notify_if_filled"),
    

    path('ticker/', views.ajax_ticker, name="ajax_ticker"),
    path('assets/', views.ajax_assets, name="ajax_assets"),
    
    path('orders/', views.ajax_orders, name="ajax_orders"),
    
    path('alerts/', views.ajax_alerts, name="ajax_alerts"),
   

    path('inquiry/', views.ajax_inquiry, name="ajax_inquiry"),
    path('attachment/', views.ajax_attachment, name="ajax_attachment"),
    path('order/', views.MainPage.as_view(), name='order'),
]