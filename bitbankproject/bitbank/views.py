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
from django.contrib.auth import authenticate
from django.core.mail import send_mail, EmailMultiAlternatives
from .forms import (LoginForm, MyPasswordChangeForm, MyPasswordResetForm,
                    MySetPasswordForm, UserCreateForm, UserUpdateForm)
from .models import User, Alert, Order, BitbankOrder, Inquiry, Attachment
from django.conf import settings
from .serializer import BitbankOrderSerializer, OrderSerializer

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


def ajax_user(request):
    if request.user.is_anonymous:
        return JsonResponse({'error' : 'authentication failed'}, status=401)

    method = request.method
    pk = request.user.pk

    if method == 'GET':
        user_qs = User.objects.filter(pk=pk)
        serialized_qs = serializers.serialize('json', user_qs)
        data = {
            'user': serialized_qs
        }
        return JsonResponse(data)
    elif method == 'POST':
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

def ajax_alerts(request):
    if request.user.is_anonymous:
        return JsonResponse({'error' : 'authentication failed'}, status=401)

    user = request.user
    method = request.method

    if method == 'GET':
        try:
            offset = int(request.GET.get('offset'))
            to = int(request.GET.get('limit')) + offset
            search_pair = request.GET.get('pair')
            if search_pair == 'all':
                alerts = Alert.objects.filter(user=user).filter(is_active=True)
            else:
                alerts = Alert.objects.filter(user=user).filter(is_active=True).filter(pair=search_pair)
                
            data = {
                'total_count': alerts.count(),
                'active_alerts': serializers.serialize('json', alerts[offset:to])
            }
        except Exception as e:
            data = {
                'error': e.args
            }
            traceback.print_exc()
        finally:
            return JsonResponse(data)
    elif method == 'POST':
        op = request.POST.get('method')
        if op == 'DELETE':
            pk = request.DELETE.get('pk')
            try:
                alert = Alert.objects.filter(pk=pk).update(is_active=False)
                return JsonResponse({'success': 'success'})
            except Exception as e:
                traceback.print_exc()
                return JsonResponse({'error': e.args})
        elif op == 'POST':
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
def ajax_ticker(request):
    if request.user.is_anonymous:
        return JsonResponse({'error' : 'authentication failed'}, status=401)
    if request.method == 'GET':
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

def ajax_assets(request):
    if request.user.is_anonymous:
        return JsonResponse({'error' : 'authentication failed'}, status=401)
    if request.method == 'GET':
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

def validate_input(obj):
    
    if not obj == None:
        if obj.start_amount == '' or obj.start_amount == '0':
            return {'error': '新規注文数量は必須です'}
        if obj.order_type in {BitbankOrder.TYPE_LIMIT, BitbankOrder.TYPE_STOP_LIMIT} and obj.price == None:
            return {'error': '新規注文の価格は必須です'}
        if obj.order_type in {BitbankOrder.TYPE_STOP_MARKET, BitbankOrder.TYPE_STOP_LIMIT} and obj.price_for_stop == None:
            return {'error': '新規注文の発動価格は必須です'}

    return {'success': True}

def process_order(user, order_obj, order_params, which_order, is_ready):
    pair = order_params.get('pair')
    side = order_params.get('side')
    order_type = order_params.get('order_type')
    price = None if order_params.get('price') == '' else order_params.get('price')
    price_for_stop = None if order_params.get('price_for_stop') == '' else order_params.get('price_for_stop')
    start_amount = order_params.get('start_amount')

    order_id = None

    if is_ready:
        status = BitbankOrder.STATUS_READY_TO_ORDER
    else:
        status = BitbankOrder.STATUS_WAIT_OTHER_ORDER_TO_FILL

    ordered_at = None
    
    if order_type in {BitbankOrder.TYPE_MARKET, BitbankOrder.TYPE_LIMIT} and is_ready:       
        try:
            res_dict = python_bitbankcc.private(user.api_key, user.api_secret_key).order(
                pair,
                price,
                start_amount,
                side,
                order_type
            )
            status = res_dict.get('status')
            order_id = res_dict.get('order_id')
            ordered_at = res_dict.get('ordered_at')

        except Exception as e:
            return {'error': e.args}

    new_bitbank_order = BitbankOrder()
    new_bitbank_order.pair = pair
    new_bitbank_order.side = side
    new_bitbank_order.order_type = order_type
    new_bitbank_order.price = price
    new_bitbank_order.price_for_stop = price_for_stop
    new_bitbank_order.start_amount = start_amount
    new_bitbank_order.order_id = order_id
    new_bitbank_order.status = status
    new_bitbank_order.ordered_at = ordered_at
    new_bitbank_order.save()

    order_obj.user = user
    order_obj.pair = pair
    order_obj.special_order = special_order
    
    if which_order == 'order_1':
        order_obj.order_1 = new_bitbank_order
    elif which_order == 'order_2':
        order_obj.order_2 = new_bitbank_order
    elif which_order == 'order_3':
        order_obj.order_3 = new_bitbank_order

    order_obj.save()
    return {'success': True}

def ajax_orders(request):
    if request.user.is_anonymous:
        return JsonResponse({'error' : 'authentication failed'}, status=401)

    user = request.user
    method = request.method
    print(method)
    if method == 'GET': 
        print(request.GET.get('type'))
        if request.GET.get('type') == 'active':
           
            offset = int(request.GET.get('offset'))
            to = int(request.GET.get('limit')) + offset
            search_pair = request.GET.get('pair')

            if search_pair == "all":
                active_orders = Order.objects.filter(user=user).filter(is_active = True).order_by('-pk')
            
            else:
                active_orders = Order.objects.filter(user=user).filter(is_active = True).filter(pair=search_pair).order_by('-pk')

            data = {
                'total_count': active_orders.count(),
                'data': OrderSerializer(active_orders[offset:to], many=True ).data
            }
            return JsonResponse(data)
           
        elif request.GET.get('type') == 'history':
            try:
                offset = int(request.GET.get('offset'))
                to = int(request.GET.get('limit')) + offset
                search_pair = request.GET.get('pair')
                if search_pair == 'all':
                    order_history = Order.objects.filter(user=user).filter(is_active = False).order_by('-pk')
                else:
                    order_history = Order.objects.filter(user=user).filter(is_active = False).filter(pair=search_pair).order_by('-pk')
                
                data = {
                    'total_count': order_history.count(),
                    'data': OrderSerializer(order_history[offset:to], many=True).data
                }
                return JsonResponse(data)
            except Exception as e:
                return JsonResponse({'error': e.args})

    elif method == 'POST':
        op = request.POST.get('method')
        print(op)
        if op == 'POST':
            print(op)
            if user.api_key == "" or user.api_secret_key == "":
                res = {
                    'error': 'API KEYが登録されていません'
                }
                return JsonResponse(res)
            
            user = request.user
            pair = request.POST.get('pair')
            special_order = request.POST.get('special_order')
            
            if special_order == 'SINGLE':
                params_1 =  json.loads(request.POST.get('order_1'))
                validate_1 = validate_input(params_1)
                if 'error' in validate_1:
                    return JsonResponse(validate_1)

                new_order_1 = Order()
                result = process_order(user, new_order_1, params_1, 'order_1', True)
                if 'error' in result:
                    return JsonResponse(result)
                new_order_1.save()
                return JsonResponse(result)

            elif special_order == 'IFD':
                params_1 =  json.loads(request.POST.get('order_1'))
                params_2 =  json.loads(request.POST.get('order_2'))
                validate_1 = validate_input(params_1)
                if 'error' in validate_1:
                    return JsonResponse(validate_1)
                validate_2 = validate_input(params_2)
                if 'error' in validate_2:
                    return JsonResponse(validate_2)
                
                new_order_1 = Order()
                result_1 = process_order(user, new_order_1, params_1, 'order_1', True)
                if 'error' in result_1:
                    return JsonResponse(result_1)
                
                new_order_2 = Order()
                result_2 = process_order(user, new_order_2, params_2, 'order_2', False)
                if 'error' in result_2:
                    return JsonResponse(result_2)

                new_order_1.save()
                new_order_2.save()

                return JsonResponse({'success': True})

            else:
                return JsonResponse({'error': '特殊注文は未対応です'})
        elif op == 'DELETE':
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

def ajax_notify_if_filled(request):
    if request.user.is_anonymous:
        return JsonResponse({'error' : 'authentication failed'}, status=401)

    if request.method == 'GET':
        res = {
            'notify_if_filled': request.user.notify_if_filled
        }
        return JsonResponse(res)

    elif request.method == 'POST':
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
        finally:    
            return JsonResponse(res)

def ajax_attachment(request):
    if request.user.is_anonymous:
        return JsonResponse({'error': 'authentication failed'}, status=401)

    method = request.method

    if method == 'POST':
        if request.POST.get('method') == 'DELETE':
            pk = request.POST.get('pk')
            Attachment.objects.filter(pk=pk).delete()
            return JsonResponse({'success': True})
        else:
            a = Attachment()
            a.file = request.FILES['attachment']
            a.save()
            return JsonResponse({'success': True, 'pk': a.pk, 'url': a.file.url})
       
def ajax_inquiry(request):
    if request.user.is_anonymous:
        return JsonResponse({'error': 'authentication failed'}, status=401)

    if request.method == 'POST':       
        try:
            new_inquiry = Attachment()
            new_inquiry.file = request.FILES['attachment']
            new_inquiry.subject = request.POST.get('subject')
            new_inquiry.body = request.POST.get('body')
            new_inquiry.email_for_reply = request.POST.get('email_for_reply')
            
            attachments = request.FILES.getlist('attachments[]')
            
            if (len(attachments) >= 1):
                print('here')
                new_inquiry.attachment_1 = attachments[0]
            if (len(attachments) >= 2):
                new_inquiry.attachment_2 = attachments[1]
            if (len(attachments) >= 3):
                new_inquiry.attachment_3 = attachments[2]
        
            new_inquiry.save()
        
            context = {
                'new_inquiry': new_inquiry,
            }

            subject_template = get_template('bitbank/mail_template/inquiry/subject.txt')
            subject = subject_template.render(context)
            
            message_template = get_template('bitbank/mail_template/inquiry/message.txt')
            message = message_template.render(context)
            
            kwargs = dict(
                to = [settings.DEFAULT_FROM_EMAIL],
                from_email = [settings.DEFAULT_FROM_EMAIL],
                subject = subject,
                body = message,
            )
            msg = EmailMultiAlternatives(**kwargs)
            if (len(attachments) >= 1):
                msg.attach_file(new_inquiry.attachment_1.path)
            if (len(attachments) >= 2):
                msg.attach_file(new_inquiry.attachment_2.path)
            if (len(attachments) >= 3):
                msg.attach_file(new_inquiry.attachment_3.path)

            msg.send()
            
            return JsonResponse({'success': '問い合わせが完了しました'})
        except Exception as e:
            return JsonResponse({'error': e.args})
    