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
from .models import Order
from django.urls import reverse

import os, json, python_bitbankcc

User = get_user_model()

class Top(generic.TemplateView):
    template_name = 'bitbank/top.html'

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
    template_name = 'bitbank/top.html'

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

        """bitbank api """
        self.object = form.save(commit = False)
        self.object.user = self.request.user
  
        order_type = form.cleaned_data['order_type']

        if order_type in {'成行', '指値'}:
            if order_type == '成行':
                order_type_rome = 'market'
            elif order_type == '指値':
                order_type_rome = 'limit'

            if self.request.api_key != "" and self.request.user.api_secret_key != "":
                try:
                    res_dict = python_bitbankcc.private(user.api_key, user.api_secret_key).order( \
                        form.cleaned_data['pair'], \
                        form.cleaned_data['price'], \
                        form.cleaned_data['start_amount'], \
                        form.cleaned_data['side'], \
                        order_type_rome
                    )
                    # エラーコードがセットされている場合
                    if 'code' in res_dict:
                        self.object.status = res_dict('code')
                    else:
                        # 正常に処理された場合
                        self.object.order_id = res_dict.get('order_id')
                        self.object.status = res_dict.get('status')
                except:
                    self.object.status = "通信エラー"

            else:
                self.object.status = "API KEY未登録"

        self.object.save()

        return http.HttpResponseRedirect(self.get_success_url())

    def get_success_url(self):
        return reverse('bitbank:order_detail', kwargs={'pk' : self.object.pk})

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)


class OrderDetail(LoginRequiredMixin, generic.DetailView):
    """注文詳細"""
    model = Order
    template_name = 'bitbank/order_detail.html'

class OrderList(LoginRequiredMixin, generic.ListView):
    """注文一覧"""
    model = Order
    template_name = 'bitbank/order_list.html'

def ajax_get_assets(request):
    user = request.user

    if user.api_key == "" or user.api_secret_key == "":
        res_dict = {
            'error': 'API KEYが登録されていません'
        }
    else:
        try:
            res_dict = python_bitbankcc.private(user.api_key, user.api_secret_key).get_asset()
        except:
            res_dict =  {
                'error': '通信エラー'
            }

    return JsonResponse(res_dict)

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
        except:
            res_dict = {
                'error': '通信エラー'
            }
            
    return JsonResponse(res_dict)