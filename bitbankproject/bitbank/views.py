import json
import logging
import os
import traceback

import python_bitbankcc
from django import forms, http
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model
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
from django.core.mail import EmailMultiAlternatives, send_mail
from django.core.signing import BadSignature, SignatureExpired, dumps, loads
from django.forms.utils import ErrorList
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, resolve_url
from django.template.loader import get_template
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import generic

from . import _util
from .forms import (LoginForm, MyPasswordChangeForm, MyPasswordResetForm,
                    MySetPasswordForm, UserCreateForm, UserUpdateForm)
from .models import (Alert, Attachment, BitbankOrder, Inquiry, OrderRelation,
                     User)
from .serializer import BitbankOrderSerializer, OrderSerializer, UserSerializer

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
    if request.user.is_anonymous or request.user.is_active == False:
        return JsonResponse({'error' : 'authentication failed'}, status=401)

    method = request.method
    if method == 'GET':
        serizlized = UserSerializer(request.user, many=False).data
        
        return JsonResponse(serizlized)

    elif method == 'POST':
        new_full_name = request.POST.get("full_name")
        new_api_key = request.POST.get("api_key")
        new_api_secret_key = request.POST.get("api_secret_key")
        new_email_for_notice = request.POST.get("email_for_notice")
        new_notify_if_filled = request.POST.get('notify_if_filled')
        new_use_alert = request.POST.get('use_alert')
        
        try:
            user_to_update = request.user
            if new_full_name != None and new_full_name != "": 
                user_to_update.full_name = new_full_name
            if new_api_key != None and new_api_key != "":
                user_to_update.api_key = new_api_key
            if new_api_secret_key != None and new_api_secret_key != "":
                user_to_update.api_secret_key = new_api_secret_key
            if new_email_for_notice != None and new_email_for_notice != "":
                user_to_update.email_for_notice = new_email_for_notice
            if new_notify_if_filled != None and new_notify_if_filled != "":
                user_to_update.notify_if_filled = new_notify_if_filled
            if new_use_alert != None and new_use_alert != "":
                user_to_update.use_alert = new_use_alert

            user_to_update.save()
        except Exception as e:
            return JsonResponse({'error': e.args})

        data = {
            'success': True
        }
        return JsonResponse(data) 

def ajax_alerts(request):
    if request.user.is_anonymous or request.user.is_active == False:
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
            pk = request.POST.get('pk')
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
    if request.user.is_anonymous or request.user.is_active == False:
        return JsonResponse({'error' : 'authentication failed'}, status=401)

    if request.method == 'GET':
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
    if request.user.is_anonymous or request.user.is_active == False:
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
        if obj.get('start_amount') == '' or obj.get('start_amount') == '0':
            return {'error': '新規注文数量は必須です'}
        if obj.get('order_type') in {BitbankOrder.TYPE_LIMIT, BitbankOrder.TYPE_STOP_LIMIT} and obj.get('price') == None:
            return {'error': '新規注文の価格は必須です'}
        if obj.get('order_type') in {BitbankOrder.TYPE_STOP_MARKET, BitbankOrder.TYPE_STOP_LIMIT} and obj.get('price_for_stop') == None:
            return {'error': '新規注文の発動価格は必須です'}

    return {'success': True}

def process_order(user, order_params, is_ready):
    prv = python_bitbankcc.private(user.api_key, user.api_secret_key)
    new_bitbank_order = BitbankOrder()
    new_bitbank_order.user = user
    new_bitbank_order.pair = order_params.get('pair')
    new_bitbank_order.side = order_params.get('side')
    new_bitbank_order.order_type = order_params.get('order_type')
    new_bitbank_order.price = None if new_bitbank_order.order_type.find('limit') == -1 else order_params.get('price')
    print(new_bitbank_order.price)
    new_bitbank_order.price_for_stop = None if new_bitbank_order.order_type.find('stop') == -1 else order_params.get('price_for_stop')
    new_bitbank_order.start_amount = order_params.get('start_amount')
    new_bitbank_order.order_id = None
    if is_ready:
        new_bitbank_order.status = BitbankOrder.STATUS_READY_TO_ORDER
    else:
        new_bitbank_order.status = BitbankOrder.STATUS_WAIT_OTHER_ORDER_TO_FILL
    new_bitbank_order.save()

    if new_bitbank_order.order_type in {BitbankOrder.TYPE_MARKET, BitbankOrder.TYPE_LIMIT} and is_ready:       
        _util.place_order(prv, new_bitbank_order)

    return new_bitbank_order

def ajax_orders(request):
    if request.user.is_anonymous or request.user.is_active == False:
        return JsonResponse({'error' : 'authentication failed'}, status=401)

    user = request.user
    prv = python_bitbankcc.private(user.api_key, user.api_secret_key)
    method = request.method
    if method == 'GET': 
        print(request.GET.get('type'))
        if request.GET.get('type') == 'active':
           
            offset = int(request.GET.get('offset'))
            to = int(request.GET.get('limit')) + offset
            search_pair = request.GET.get('pair')

            if search_pair == "all":
                active_orders = OrderRelation.objects.filter(user=user).filter(is_active = True).order_by('-pk')
            
            else:
                active_orders = OrderRelation.objects.filter(user=user).filter(is_active = True).filter(pair=search_pair).order_by('-pk')

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
                    order_history = BitbankOrder.objects.filter(user=user).filter(status__in=[BitbankOrder.STATUS_CANCELED_PARTIALLY_FILLED, BitbankOrder.STATUS_FULLY_FILLED, BitbankOrder.STATUS_FAILED_TO_ORDER]).order_by('-pk')
                else:
                    order_history = BitbankOrder.objects.filter(user=user).filter(status__in=[BitbankOrder.STATUS_CANCELED_PARTIALLY_FILLED, BitbankOrder.STATUS_FULLY_FILLED, BitbankOrder.STATUS_FAILED_TO_ORDER]).filter(pair=search_pair).order_by('-pk')
                
                data = {
                    'total_count': order_history.count(),
                    'data': BitbankOrderSerializer(order_history[offset:to], many=True).data
                }
                return JsonResponse(data)
            except Exception as e:
                return JsonResponse({'error': e.args})

    elif method == 'POST':
        if user.api_key == "" or user.api_secret_key == "":
            res = {
                'error': 'API KEYが登録されていません'
            }
            return JsonResponse(res)
        op = request.POST.get('method')
        
        
        if op == 'POST':

            pair = request.POST.get('pair')
            special_order = request.POST.get('special_order')
            
            if special_order == 'SINGLE':
                params_1 =  json.loads(request.POST.get('order_1'))
                validate_1 = validate_input(params_1)
                if 'error' in validate_1:
                    return JsonResponse(validate_1)

                new_order = OrderRelation()
                new_order.user = user
                new_order.pair = pair
                new_order.special_order = special_order
                o_1 = process_order(user, params_1, True)
                if o_1.status == BitbankOrder.STATUS_FAILED_TO_ORDER:
                    new_order = None
                    return JsonResponse({'error': o_1.error_message})
                new_order.order_1 = o_1
                new_order.is_active = True
                new_order.save()
                return JsonResponse({'success': True})

            elif special_order == 'IFD':
                params_1 =  json.loads(request.POST.get('order_1'))
                params_2 =  json.loads(request.POST.get('order_2'))
                validate_1 = validate_input(params_1)
                if 'error' in validate_1:
                    return JsonResponse(validate_1)
                validate_2 = validate_input(params_2)
                if 'error' in validate_2:
                    return JsonResponse(validate_2)
                
                new_order = OrderRelation()
                new_order.user = user
                new_order.pair = pair
                new_order.special_order = special_order
                o_1 = process_order(user, params_1, True)
                new_order.order_1 = o_1
                if o_1.status == BitbankOrder.STATUS_FAILED_TO_ORDER:
                    return JsonResponse({'error': True})
                

                o_2 = process_order(user, params_2, False)
                new_order.order_2 = o_2
                if o_2.status == BitbankOrder.STATUS_FAILED_TO_ORDER:
                    _util.cancel_order(prv, o_1)
                    return JsonResponse({'error': o_2.error_message})

                new_order.is_active = True
                new_order.save()

                return JsonResponse({'success': True})

            elif special_order == 'OCO':
                params_2 =  json.loads(request.POST.get('order_2'))
                params_3 =  json.loads(request.POST.get('order_3'))
                validate_2 = validate_input(params_2)
                if 'error' in validate_2:
                    return JsonResponse(validate_2)
                validate_3 = validate_input(params_3)
                if 'error' in validate_3:
                    return JsonResponse(validate_3)
                
                new_order = OrderRelation()
                new_order.user = user
                new_order.pair = pair
                new_order.special_order = special_order
                o_2 = process_order(user, params_2, True)
                new_order.order_2 = o_2
                if o_2.status == BitbankOrder.STATUS_FAILED_TO_ORDER:
                    return JsonResponse({'error': o_2.error_message})
                
                o_3 = process_order(user, params_3, True)
                new_order.order_3 = o_3
                if o_3.status == BitbankOrder.STATUS_FAILED_TO_ORDER:
                    _util.cancel_order(prv, o_2)
                    return JsonResponse({'error': o_3.error_message})
                new_order.is_active = True
                new_order.save()
                return JsonResponse({'success': True})
            elif special_order == 'IFDOCO':
                params_1 =  json.loads(request.POST.get('order_1'))
                params_2 =  json.loads(request.POST.get('order_2'))
                params_3 =  json.loads(request.POST.get('order_3'))

                validate_1 = validate_input(params_1)
                if 'error' in validate_1:
                    return JsonResponse(validate_1)
                
                validate_2 = validate_input(params_2)
                if 'error' in validate_2:
                    return JsonResponse(validate_2)
                validate_3 = validate_input(params_3)
                if 'error' in validate_3:
                    return JsonResponse(validate_3)
                
                new_order = OrderRelation()
                new_order.user = user
                new_order.pair = pair
                new_order.special_order = special_order

                o_1 = process_order(user, params_1, True)
                new_order.order_1 = o_1
                if o_1.status == BitbankOrder.STATUS_FAILED_TO_ORDER:
                    return JsonResponse({'error': o_1.error_message})
                
                o_2 = process_order(user, params_2, False)
                new_order.order_2 = o_2
                if o_2.status == BitbankOrder.STATUS_FAILED_TO_ORDER:
                    return JsonResponse({'error': o_2.error_message})
                
                o_3 = process_order(user, params_3, False)
                new_order.order_3 = o_3
                if o_3.status == BitbankOrder.STATUS_FAILED_TO_ORDER:
                    _util.cancel_order(prv, o_2)
                    return JsonResponse({'error': o_3.error_message})
                new_order.is_active = True
                new_order.save()
                return JsonResponse({'success': True})

        elif op == 'DELETE':
            pk = request.POST.get("pk")
            
            cancel_succeeded = True
            subj_order = BitbankOrder.objects.filter(pk = pk).get()
            if subj_order.order_id != None:
                cancel_succeeded = _util.cancel_order(prv, subj_order)
            else:
                # 未発注の場合はステータスをキャンセル済みに変更
                subj_order.status = 'CANCELED_UNFILLED'
                subj_order.save()
            if cancel_succeeded:
                
                if OrderRelation.objects.filter(order_1 = subj_order).count() > 0:
                    relation = OrderRelation.objects.get(order_1 = subj_order)
                    relation.is_active = False

                elif OrderRelation.objects.filter(order_2 = subj_order).count() > 0:
                    relation = OrderRelation.objects.get(order_2 = subj_order)
                    # IFD
                    if relation.order_3 == None:
                        relation.order_2 = None
                        relation.special_order = 'SINGLE'
                    # OCO
                    elif relation.order_1 == None:
                        relation.order_1 = relation.order_3
                        relation.order_2 = None
                        relation.order_3 = None
                        relation.special_order = 'SINGLE'
                    # IFDOCO
                    else:
                        relation.order_2 = relation.order_3
                        relation.order_3 = None
                        relation.special_order = 'IFD'

                elif OrderRelation.objects.filter(order_3 = subj_order).count() > 0:
                    relation = OrderRelation.objects.get(order_3 = subj_order)
                    # OCO
                    if relation.order_1 == None:
                        relation.order_1 = relation.order_2
                        relation.order_2 = None
                        relation.order_3 = None
                        relation.special_order = 'SINGLE'
                    # IFDOCO
                    else:
                        relation.order_3 = None
                        relation.special_order = 'IFD'
                relation.save()
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'error': 'この注文はキャンセルできません'})
            # except Exception as e:
            #     return JsonResponse({'error': e.args})
                

def ajax_attachment(request):
    if request.user.is_anonymous or request.user.is_active == False:
        return JsonResponse({'error' : 'authentication failed'}, status=401)

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
    if request.user.is_anonymous or request.user.is_active == False:
        return JsonResponse({'error' : 'authentication failed'}, status=401)
        
    if request.method == 'POST':       
        try:
            new_inquiry = Inquiry()
            new_inquiry.user = request.user
            new_inquiry.subject = request.POST.get('subject')
            new_inquiry.body = request.POST.get('body')
            new_inquiry.email_for_reply = request.POST.get('email_for_reply')
            print(request.POST.get('email_for_reply'))
            att_1_pk = request.POST.get('att_pk_1')
            att_2_pk = request.POST.get('att_pk_2')
            att_3_pk = request.POST.get('att_pk_3')
            
            if att_1_pk != None and att_1_pk != '':
                new_inquiry.attachment_1 = Attachment.objects.get(pk = att_1_pk)
            if att_2_pk != None and att_2_pk != '':
                new_inquiry.attachment_2 = Attachment.objects.get(pk = att_2_pk)
            if att_3_pk != None and att_3_pk != '':
                new_inquiry.attachment_3 = Attachment.objects.get(pk = att_3_pk)
            
            new_inquiry.save()
        
            context = {
                'new_inquiry': new_inquiry,
            }

            subject_template_for_admin = get_template('bitbank/mail_template/inquiry/subject.txt')
            subject_for_admin = subject_template_for_admin.render(context)
            message_template_for_admin = get_template('bitbank/mail_template/inquiry/message.txt')
            message_for_admin = message_template_for_admin.render(context)

            subject_template_for_customer = get_template('bitbank/mail_template/inquiry/subject_for_customer.txt')
            subject_for_customer = subject_template_for_customer.render(context)
            message_template_for_customer = get_template('bitbank/mail_template/inquiry/message_for_customer.txt')
            message_for_customer = message_template_for_customer.render(context)

            kwargs_for_admin = dict(
                to = [settings.DEFAULT_FROM_EMAIL],
                from_email = settings.DEFAULT_FROM_EMAIL,
                subject = subject_for_admin,
                body = message_for_admin,
            )
            kwargs_for_customer = dict(
                to = [request.POST.get('email_for_reply')],
                from_email = settings.DEFAULT_FROM_EMAIL,
                subject = subject_for_customer,
                body = message_for_customer,
            )
            msg_for_admin = EmailMultiAlternatives(**kwargs_for_admin)
            msg_for_customer = EmailMultiAlternatives(**kwargs_for_customer)
            
            if (new_inquiry.attachment_1 != None):
                msg_for_admin.attach_file(new_inquiry.attachment_1.file.path)
                msg_for_customer.attach_file(new_inquiry.attachment_1.file.path)
                
            if (new_inquiry.attachment_2 != None):
                msg_for_admin.attach_file(new_inquiry.attachment_2.file.path)
                msg_for_customer.attach_file(new_inquiry.attachment_2.file.path)
                
            if (new_inquiry.attachment_3 != None):
                msg_for_admin.attach_file(new_inquiry.attachment_3.file.path)
                msg_for_customer.attach_file(new_inquiry.attachment_3.file.path)

            msg_for_admin.send()
            msg_for_customer.send()
            return JsonResponse({'success': '問い合わせが完了しました'})
        except Exception as e:
            return JsonResponse({'error': e.args})
