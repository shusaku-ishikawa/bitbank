import traceback
from django import forms
from django.contrib import messages
from django import http
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.auth.views import (
    LoginView, LogoutView, PasswordChangeView, PasswordChangeDoneView,
    PasswordResetView, PasswordResetDoneView, PasswordResetConfirmView, PasswordResetCompleteView
)
from django.urls import reverse_lazy
from django.contrib.sites.shortcuts import get_current_site
from django.core.signing import BadSignature, SignatureExpired, loads, dumps
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, resolve_url
from django.template.loader import get_template
from django.views import generic
from .forms import (
    LoginForm, UserCreateForm, UserUpdateForm, MyPasswordChangeForm,
    MyPasswordResetForm, MySetPasswordForm, MyOrderForm
)
from django.core import serializers
from .models import Order, Alert
from django.urls import reverse
from django.utils import timezone
from django.forms.utils import ErrorList

import os, json, python_bitbankcc

User = get_user_model()

class Login(LoginView):
    """ログインページ"""
    form_class = LoginForm
    template_name = 'bitbank/login.html'

class OnlyYouMixin(UserPassesTestMixin):
    raise_exception = True

    def test_func(self):
        user = self.request.user
        return user.pk == self.kwargs['pk'] or user.is_superuser


class UserDetail(OnlyYouMixin, generic.DetailView):
    model = User
    template_name = 'bitbank/user_detail.html'


class UserUpdate(OnlyYouMixin, generic.UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = 'bitbank/user_form.html'

    def get_success_url(self):
        return resolve_url('bitbank:user_detail', pk=self.kwargs['pk'])

class Logout(LoginRequiredMixin, LogoutView):
    """ログアウトページ"""
    template_name = 'bitbank/logout.html'

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


class OrderCreate(LoginRequiredMixin, generic.CreateView):
    """注文登録"""
    model = Order
    template_name = 'bitbank/order_create.html'
    form_class = MyOrderForm

    def form_valid(self, form):
        if self.request.user.api_key == "" or self.request.user.api_secret_key == "":
            form._errors[forms.forms.NON_FIELD_ERRORS] = ErrorList([
                u'APIキーが登録されていません'
            ])
            return self.form_invalid(form)

        order_type = form.cleaned_data['order_type']

        if order_type in {'成行', '指値'}:
            if order_type == '成行':
                order_type_rome = 'market'
            elif order_type == '指値':
                order_type_rome = 'limit'
                # 指値の場合は金額必須
                if form.cleaned_data['price'] == 0 or form.cleaned_data['price'] == '' or form.cleaned_data['price'] == None:
                    form._errors[forms.forms.NON_FIELD_ERRORS] = ErrorList([
                        u'指値の際は価格を入力してください'
                    ])
                    return self.form_invalid(form)

            try:
                res_dict = python_bitbankcc.private(self.request.user.api_key, self.request.user.api_secret_key).order(
                    form.cleaned_data['pair'],
                    form.cleaned_data['price'],
                    form.cleaned_data['start_amount'],
                    form.cleaned_data['side'],
                    order_type_rome
                )
            except Exception as e:
                traceback.print_exc()
                form._errors[forms.forms.NON_FIELD_ERRORS] = ErrorList([
                    e.args
                ])
                return self.form_invalid(form)
            self.object = form.save(commit = False)
            self.object.order_id = res_dict.get('order_id')
            self.object.status = res_dict.get('status')
            self.object.ordered_at = res_dict.get('ordered_at')
            messages.success(self.request, '注文が完了しました')

        elif order_type in {'逆指値', 'ストップリミット'}:
            # 金額必須
            if form.cleaned_data['price'] == 0 or form.cleaned_data['price'] == '' or form.cleaned_data['price'] == None:
                form._errors[forms.forms.NON_FIELD_ERRORS] = ErrorList([
                    u'指値の際は価格を入力してください'
                ])
                return self.form_invalid(form)


            if order_type == '逆指値':
                order_type_rome = 'market'
            elif order_type == 'ストップリミット':
                order_type = 'limit'
                # 逆指値価格必須
                if form.cleaned_data['price_for_stop_limit'] == 0 or form.cleaned_data['price_for_stop_limit'] == '' or form.cleaned_data['price_for_stop_limit'] == None:
                    form._errors[forms.forms.NON_FIELD_ERRORS] = ErrorList([
                        u'ストップリミットの際は逆指値価格を入力してください'
                    ])
                    return self.form_invalid(form)
            # オブジェクト作成
            self.object = form.save(commit = False)
            self.object.order_id = None
            self.object.status = None
            self.object.ordered_at = None
            messages.success(self.request, 'ストップ注文を正常に受け付けました')

        # 共通項目セット、保存
        self.object.user = self.request.user
        self.object.save()

        return http.HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('bitbank:order')

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        context = super(OrderCreate, self).get_context_data(**kwargs)
        # context['active_orders'] = Order.objects.filter(user=self.request.user).filter(status__in=['UNFILLED', 'PARTIALLY_FILLED'])
        # context['order_history'] = Order.objects.filter(user=self.request.user).filter(order_id__isnull=False)
        # context['stop_orders'] = Order.objects.filter(user=self.request.user).filter(order_type__in=['逆指値', 'ストップリミット']).filter(order_id__isnull=True)
        # context['alerts'] = Alert.objects.filter(user=self.request.user).filter(is_active="有効")
        
        return context

class OrderDetail(LoginRequiredMixin, generic.DetailView):
    """注文詳細"""
    model = Order
    template_name = 'bitbank/order_detail.html'

def ajax_create_alert(request):
    user = request.user
    pair = request.POST.get('pair')
    threshold = request.POST.get('threshold')
    over_or_under = request.POST.get('over_or_under')
    try:
        new_alert = Alert(user=user, pair=pair, threshold=threshold, over_or_under=over_or_under, is_active=True, alerted_at=None)
        new_alert.save()
        data = {
            'success': 'success',
            'pk': new_alert.pk
        }
    except Exception as e:
        data = {
            'error': e.args
        }
        traceback.print_exc()
    finally:
        return JsonResponse(data)

def ajax_deactivate_alert(request):
    user = request.user
    pk = request.POST.get('pk')
    
    try:
        alert = Alert.objects.filter(pk=pk).update(is_active=False)
        
        data = {
            'success': 'success'
        }
    except Exception as e:
        data = {
            'error': e.args
        }
        traceback.print_exc()
    finally:
        return JsonResponse(data)

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
    
    active_orders = Order.objects.filter(user=user).filter(status__in=['UNFILLED', 'PARTIALLY_FILLED'])
    serialized_qs = serializers.serialize('json', active_orders)
    data = {
        'active_orders': serialized_qs
    }
    return JsonResponse(data)

def ajax_get_stop_orders(request):
    user = request.user
    
    stop_orders = Order.objects.filter(user=user).filter(order_type__in=['逆指値', 'ストップリミット']).filter(order_id__isnull=True)
    serialized_qs = serializers.serialize('json', stop_orders)
    data = {
        'stop_orders': serialized_qs
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
        res_dict = {
            'error': 'API KEYが登録されていません'
        }
    else:
        try:
            pair = request.POST.get("pair")
            order_id = request.POST.get("order_id")
            res_dict = python_bitbankcc.private(user.api_key, user.api_secret_key).cancel_order(pair, order_id)
            subj_order = Order.objects.filter(order_id = order_id).get()
            subj_order.status = res_dict.get("status")
            subj_order.save()
        except Exception as e:
            res_dict = {
                'error': e.args
            }
            traceback.print_exc()
            
    return JsonResponse(res_dict)

def ajax_cancel_stop_order(request):
    user = request.user
    pk = request.POST.get('pk')

    order_to_delete = Order.objects.get(pk=pk)
    if order_to_delete.order_id != None:
        date = {
            'error': '既に注文済みです。アクティブ注文より取消を実施してください'
        }
    else:
        try:
            order_to_delete.delete()
            data = {
                'success': 'success'
            }
        except Exception as e:
            data = {
                'error': e.args
            }
        
    return JsonResponse(data)