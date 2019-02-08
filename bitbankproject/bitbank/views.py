import json
import logging
import os
import traceback

import python_bitbankcc
from django import forms, http
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import (LoginView, LogoutView,
                                       PasswordChangeDoneView,
                                       PasswordChangeView,
                                       PasswordResetCompleteView,
                                       PasswordResetConfirmView,
                                       PasswordResetDoneView,
                                       PasswordResetView)
from django.contrib.sites.shortcuts import get_current_site
from django.core import serializers
from django.core.signing import BadSignature, SignatureExpired, dumps, loads
from django.forms.utils import ErrorList
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, resolve_url
from django.template.loader import get_template
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import generic

from .forms import (LoginForm, MyPasswordChangeForm, MyPasswordResetForm,
                    MySetPasswordForm, UserCreateForm, UserUpdateForm)
from .models import User, Alert, Order

# User = get_user_model()

class Login(LoginView):
    """ログインページ"""
    form_class = LoginForm
    template_name = 'bitbank/login.html'

class Logout(LoginRequiredMixin, LogoutView):
    """ログアウトページ"""
    template_name = 'bitbank/top.html'

class OnlyYouMixin(UserPassesTestMixin):
    raise_exception = True

    def test_func(self):
        user = self.request.user
        return user.pk == self.kwargs['pk'] or user.is_superuser



class UserCreate(generic.CreateView):
    """ユーザー仮登録"""
    template_name = 'bitbank/user_create.html'
    form_class = UserCreateForm

    def form_valid(self, form):
        """仮登録と本登録用メールの発行."""
        # 仮登録と本登録の切り替えは、is_active属性を使うと簡単です。
        # 退会処理も、is_activeをFalseにするだけにしておくと捗ります。
        user = form.save(commit=False)
        user.is_active = False
        user.save()

        # アクティベーションURLの送付
        current_site = get_current_site(self.request)
        domain = current_site.domain
        context = {
            'protocol': self.request.scheme,
            'domain': domain,
            'token': dumps(user.pk),
            'user': user,
        }

        subject_template = get_template('bitbank/mail_template/create/subject.txt')
        subject = subject_template.render(context)

        message_template = get_template('bitbank/mail_template/create/message.txt')
        message = message_template.render(context)

        user.email_user(subject, message)
        return redirect('bitbank:user_create_done')


class UserCreateDone(generic.TemplateView):
    """ユーザー仮登録したよ"""
    template_name = 'bitbank/user_create_done.html'


class UserCreateComplete(generic.TemplateView):
    """メール内URLアクセス後のユーザー本登録"""
    template_name = 'bitbank/user_create_complete.html'
    timeout_seconds = getattr(settings, 'ACTIVATION_TIMEOUT_SECONDS', 60*60*24)  # デフォルトでは1日以内

    def get(self, request, **kwargs):
        """tokenが正しければ本登録."""
        token = kwargs.get('token')
        try:
            user_pk = loads(token, max_age=self.timeout_seconds)

        # 期限切れ
        except SignatureExpired:
            return HttpResponseBadRequest()

        # tokenが間違っている
        except BadSignature:
            return HttpResponseBadRequest()

        # tokenは問題なし
        else:
            try:
                user = User.objects.get(pk=user_pk)
            except User.DoesNotExist:
                return HttpResponseBadRequest()
            else:
                if not user.is_active:
                    # 問題なければ本登録とする
                    user.is_active = True
                    user.save()
                    return super().get(request, **kwargs)

        return HttpResponseBadRequest()

class PasswordChange(PasswordChangeView):
    """パスワード変更ビュー"""
    form_class = MyPasswordChangeForm
    success_url = reverse_lazy('bitbank:password_change_done')
    template_name = 'bitbank/password_change.html'


class PasswordChangeDone(PasswordChangeDoneView):
    """パスワード変更しました"""
    template_name = 'bitbank/password_change_done.html'

class PasswordReset(PasswordResetView):
    """パスワード変更用URLの送付ページ"""
    subject_template_name = 'bitbank/mail_template/password_reset/subject.txt'
    email_template_name = 'bitbank/mail_template/password_reset/message.txt'
    template_name = 'bitbank/password_reset_form.html'
    form_class = MyPasswordResetForm
    success_url = reverse_lazy('bitbank:password_reset_done')


class PasswordResetDone(PasswordResetDoneView):
    """パスワード変更用URLを送りましたページ"""
    template_name = 'bitbank/password_reset_done.html'


class PasswordResetConfirm(PasswordResetConfirmView):
    """新パスワード入力ページ"""
    form_class = MySetPasswordForm
    success_url = reverse_lazy('bitbank:password_reset_complete')
    template_name = 'bitbank/password_reset_confirm.html'


class PasswordResetComplete(PasswordResetCompleteView):
    """新パスワード設定しましたページ"""
    template_name = 'bitbank/password_reset_complete.html'

class MainPage(LoginRequiredMixin, generic.TemplateView):
    """メインページ"""
    template_name = 'bitbank/order.html'

    def get_context_data(self, **kwargs):
        context = super(MainPage, self).get_context_data(**kwargs)
        context['notify_if_filled'] = User.objects.filter(pk=self.request.user.pk).get().notify_if_filled
        return context

def ajax_get_user(request):
    pk = request.user.pk
    user_qs = User.objects.filter(pk=pk)
    serialized_qs = serializers.serialize('json', user_qs)
    data = {
        'user': serialized_qs
    }
    return JsonResponse(data)

def ajax_update_user(request):
    pk = request.user.pk
    new_full_name = request.POST.get("full_name")
    new_api_key = request.POST.get("api_key")
    new_api_secret_key = request.POST.get("api_secret_key")
    new_email_for_notice = request.POST.get("email_for_notice")
    
    try:
        user_to_update = User.objects.get(pk=pk)
        user_to_update.full_name = new_full_name
        user_to_update.api_key = new_api_key
        user_to_update.api_secret_key = new_api_secret_key
        user_to_update.email_for_notice = new_email_for_notice
        user_to_update.save()
    except Exception as e:
        return JsonResponse({'error': e.args})

    data = {
        'success': 'success'
    }
    return JsonResponse(data)


def ajax_create_order(request):
    logger = logging.getLogger('transaction_logger')
    logger.info('transaction start')
    user = request.user
    pair = request.POST.get('pair')
    special_order = request.POST.get('special_order')

    if special_order == 'SINGLE':
        side = request.POST.get('side')
        order_type = request.POST.get('order_type')
        price = None if request.POST.get('price') == '' else request.POST.get('price')
        price_for_stop = None if request.POST.get('price_for_stop') == '' else request.POST.get('price_for_stop')
        start_amount = request.POST.get('start_amount')
        
        if start_amount == '' or start_amount == '0':
            return JsonResponse({'error': '数量は必須です'})

        order_id = None
        status = 'READY_TO_ORDER'
        ordered_at = None
        
        if order_type in {'指値', 'ストップリミット'} and price == None:
            return JsonResponse({'error': '価格は必須です'})
        
        if order_type in {'逆指値', 'ストップリミット'} and price_for_stop == None:
            return JsonResponse({'error': '発動価格は必須です'})

        if order_type in {'成行', '指値'}:
        
            if order_type == '成行':
                order_type_rome = 'market'
            elif order_type == '指値':
                order_type_rome = 'limit'
        
            try:
                res_dict = python_bitbankcc.private(request.user.api_key, request.user.api_secret_key).order(
                    pair,
                    price,
                    start_amount,
                    side,
                    order_type_rome
                )
                status = res_dict.get('status')
                order_id = res_dict.get('order_id')
                ordered_at = res_dict.get('ordered_at')

            except Exception as e:
                traceback.print_exc()
                logger.error(e.args)
                return JsonResponse({'error': e.args})
        
        new_order = Order()
        new_order.user = user
        new_order.pair = pair
        new_order.special_order = special_order
        new_order.side = side
        new_order.order_type = order_type
        new_order.price = price
        new_order.price_for_stop = price_for_stop
        new_order.start_amount = start_amount
        new_order.order_id = order_id
        new_order.status = status
        new_order.ordered_at = ordered_at
        new_order.save()
        return JsonResponse({'success': '注文が完了しました。'})
    else:
        return JsonResponse({'error': '特殊注文は未対応です'})

def ajax_create_alert(request):
    user = request.user
    pair = request.POST.get('pair')
    threshold = request.POST.get('threshold')
    over_or_under = request.POST.get('over_or_under')
    try:
        new_alert = Alert(user=user, pair=pair, threshold=threshold, over_or_under=over_or_under, is_active=True, alerted_at=None)
        new_alert.save()
        return JsonResponse({'success': 'success'})
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': e.args})

def ajax_deactivate_alert(request):
    user = request.user
    pk = request.POST.get('pk')
    
    try:
        alert = Alert.objects.filter(pk=pk).update(is_active=False)
        return JsonResponse({'success': 'success'})
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({'error': e.args})

def ajax_get_active_alerts(request):
    user = request.user
    
    try:
        alerts = Alert.objects.filter(user=user).filter(is_active=True)
        serialized_qs = serializers.serialize('json', alerts)
        
        data = {
            'active_alerts': serialized_qs
        }
    except Exception as e:
        data = {
            'error': e.args
        }
        traceback.print_exc()
    finally:
        return JsonResponse(data)


def ajax_get_ticker(request):
    user = request.user
    pair = request.GET.get('pair')
    try:
        pub = python_bitbankcc.public()
        res_dict = pub.get_ticker(pair)

    except Exception as e:
        res_dict = {
            'error': e.args
        }
        traceback.print_exc()

    return JsonResponse(res_dict)

def ajax_get_assets(request):
    user = request.user

    if user.api_key == "" or user.api_secret_key == "":
        res_dict = {
            'error': 'API KEYが登録されていません'
        }
    else:
        try:
            res_dict = python_bitbankcc.private(user.api_key, user.api_secret_key).get_asset()
        except Exception as e:
            res_dict = {
                'error': e.args
            }
            traceback.print_exc()

    return JsonResponse(res_dict)

def ajax_get_active_orders(request):
    user = request.user
    
    active_orders = Order.objects.filter(user=user).filter(status__in=['UNFILLED', 'PARTIALLY_FILLED', 'READY_TO_ORDER'])
    serialized_qs = serializers.serialize('json', active_orders)
    data = {
        'active_orders': serialized_qs
    }
    return JsonResponse(data)

  
def ajax_get_order_histroy(request):
    user = request.user
    
    order_history = Order.objects.filter(user=user).filter(order_id__isnull=False).filter(status__in=['FULLY_FILLED', 'CANCELED_UNFILLED', 'PARTIALLY_CANCELED'])
    serialized_qs = serializers.serialize('json', order_history)
    data = {
        'order_history': serialized_qs
    }
    return JsonResponse(data)

def ajax_cancel_order(request):
    user = request.user
    if user.api_key == "" or user.api_secret_key == "":
        res = {
            'error': 'API KEYが登録されていません'
        }
        return JsonResponse(res)
    pk = request.POST.get("pk")
    subj_order = Order.objects.filter(pk = pk).get()
    special_order = subj_order.special_order

    # シングル注文のキャンセル
    if special_order == 'SINGLE':
        try:    
            if subj_order.order_id != None:
                res_dict = python_bitbankcc.private(user.api_key, user.api_secret_key).cancel_order(subj_order.pair, subj_order.order_id)
                subj_order.status = res_dict.get("status")
            else:
                # 未発注の場合はステータスをキャンセル済みに変更
                subj_order.status = 'CANCELED_UNFILLED'
            
            
            subj_order.save()
            return JsonResponse({'success': 'success'})

        except Exception as e:
            return JsonResponse({'error': e.args})
            traceback.print_exc()
    else:
        return JsonResponse({'error': 'SINGLE以外の注文は現在サポートしていません'})

def ajax_get_notify_if_filled(request):
    user = request.user
    res = {
        'notify_if_filled': request.user.notify_if_filled
    }
    return JsonResponse(res)

def ajax_change_notify_if_filled(request):
    try:
        pk = request.user.pk
        new_val = request.POST.get('notify_if_filled')
        user_to_update = User.objects.get(pk=pk)
        user_to_update.notify_if_filled = new_val
        user_to_update.save()
        res = {
            'success': 'success'
        }
    except Exception as e:
        res = {
            'error': e.args
        }
    return JsonResponse(res)
