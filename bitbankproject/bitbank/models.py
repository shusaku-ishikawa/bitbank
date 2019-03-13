from django import forms
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.mail import send_mail
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from unixtimestampfield.fields import UnixTimeStampField
from django.core.files.storage import FileSystemStorage
from django.db.models.signals import post_delete
from django.dispatch import receiver
import unicodedata


class ASCIIFileSystemStorage(FileSystemStorage):
    """
    Convert unicode characters in name to ASCII characters.
    """
    def get_valid_name(self, name):
        name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore')
        return super(ASCIIFileSystemStorage, self).get_valid_name(name)

class UserManager(BaseUserManager):
    """ユーザーマネージャー."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        """メールアドレスでの登録を必須にする"""
        if not email:
            raise ValueError('The given email must be set')
        email = self.normalize_email(email)

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        """is_staff(管理サイトにログインできるか)と、is_superuer(全ての権限)をFalseに"""
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        """スーパーユーザーは、is_staffとis_superuserをTrueに"""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(email, password, **extra_fields)



class User(AbstractBaseUser, PermissionsMixin):
    def __str__(self):
        return self.full_name
        
    """カスタムユーザーモデル."""
    NOTIFY_STR = (
            ('ON', 'ON'),
            ('OFF', 'OFF')
    )
    email = models.EmailField(_('登録メールアドレス'), unique=True)
    email_for_notice = models.EmailField(_('通知用メールアドレス'), blank=True)
    full_name = models.CharField(_('名前'), max_length=150, blank=True)
    api_key = models.CharField(_('API KEY'), max_length=255, blank=True)
    api_secret_key = models.CharField(_('API SECRET KEY'), max_length=255, blank=True)
    notify_if_filled = models.CharField(
        verbose_name = _('約定通知'),
        max_length = 10,
        default = 'ON',
        choices = NOTIFY_STR,
    )
    use_alert = models.CharField(
        verbose_name = _('アラートメール通知'),
        max_length = 10,
        default = 'ON',
        choices = NOTIFY_STR,
    )

    is_staff = models.BooleanField(
        _('管理者'),
        default=False,
        help_text=_(
            'Designates whether the user can log into this admin site.'),
    )
    is_active = models.BooleanField(
        _('利用開始'),
        default=True,
        help_text=_(
            'Designates whether this user should be treated as active. '
            'Unselect this instead of deleting accounts.'
        ),
    )

    remaining_days = models.IntegerField(
        _('残日数'),
        blank = True,
        default = 0,
        validators = [
                MinValueValidator(0),
        ]
    )
    date_joined = models.DateTimeField(_('date joined'), default=timezone.now)

    objects = UserManager()

    EMAIL_FIELD = 'email'
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _('利用者')
        verbose_name_plural = _('利用者')

    def email_user(self, subject, message, from_email=None, **kwargs):
        """Send an email to this user."""
        send_mail(subject, message, from_email, [self.email_for_notice], **kwargs)
 

    @property
    def username(self):
        """username属性のゲッター

        他アプリケーションが、username属性にアクセスした場合に備えて定義
        メールアドレスを返す
        """
        return self.email



class BitbankOrder(models.Model):
    def __str__(self):
        if self.order_id == None:
            return "-"
        else:
            return self.order_id
        
    class Meta:
        verbose_name = "取引履歴"
        verbose_name_plural = "取引履歴"
        
    TYPE_MARKET = 'market'
    TYPE_LIMIT = 'limit'
    TYPE_STOP_MARKET = 'stop_market'
    TYPE_STOP_LIMIT = 'stop_limit'

    STATUS_UNFILLED = 'UNFILLED'
    STATUS_PARTIALLY_FILLED = 'PARTIALLY_FILLED'
    STATUS_FULLY_FILLED = 'FULLY_FILLED'
    STATUS_CANCELED_UNFILLED = 'CANCELED_UNFILLED'
    STATUS_CANCELED_PARTIALLY_FILLED = 'CANCELED_PARTIALLY_FILLED'
    STATUS_READY_TO_ORDER = 'READY_TO_ORDER'
    STATUS_WAIT_OTHER_ORDER_TO_FILL = "WAIT_OTHER_ORDER_TO_FILL"
    STATUS_FAILED_TO_ORDER = 'FAILED_TO_ORDER'

    PAIR = {
        'btc_jpy': 'BTC/JPY',
        'xrp_jpy': 'XRP/JPY',
        'ltc_btc': 'LTC/BTC',
        'eth_btc': 'ETH/BTC',
        'mona_jpy': 'MONA/JPY',
        'mona_btc': 'MONA/BTC',
        'bcc_jpy': 'BCC/JPY',
        'bcc_btc': 'BCC/BTC'
    }

    STATUS = {
        'UNFILLED': '未約定',
        'PARTIALLY_FILLED': '一部約定済',
        'FULLY_FILLED': '約定済',
        'CANCELED_UNFILLED': 'キャンセル済',
        'CANCELED_PARTIALLY_FILLED': '一部キャンセル済',
        'READY_TO_ORDER': '未注文',
        'FAILED_TO_ORDER': '注文失敗',
        'WAIT_OTHER_ORDER_TO_FILL': '他注文約定待'
    }
    ORDER_TYPE = {
        'market': '成行',
        'limit': '指値',
        'stop_market': '逆指値',
        'stop_limit': 'ストップリミット'
    }
    SIDE = {
        'sell': '売',
        'buy': '買'
    }
    user = models.ForeignKey(
        User,
        verbose_name = '利用者',
        on_delete = models.CASCADE
    )
   
    pair = models.CharField(
        verbose_name = _('通貨'),
        max_length = 50,
    )

    side = models.CharField(
        verbose_name = '売/買',
        max_length = 50,
    )

    order_type = models.CharField(
        verbose_name = _('注文方法'),
        max_length = 50,
    )

    price = models.FloatField(
        verbose_name = _('注文価格'),
        blank = True,
        null = True,
        validators = [
            MinValueValidator(0),
        ]
    )
    price_for_stop = models.FloatField(
        verbose_name = _('ストップ価格'),
        blank = True,
        null = True,
        validators = [
            MinValueValidator(0),
        ]
    )

    start_amount = models.FloatField(
        verbose_name = _('注文数量'),
        null = True,
        validators = [
            MinValueValidator(0.0),
        ]
    )

    remaining_amount = models.FloatField(
        verbose_name = _('未約定数量'),
        blank = True,
        null = True,
        validators = [
            MinValueValidator(0.0)
        ]
    )

    executed_amount = models.FloatField(
        verbose_name = _('約定済数量'),
        blank = True,
        null = True,
        validators = [
            MinValueValidator(0.0)
        ]
    )

    average_price = models.FloatField(
        verbose_name = _('約定平均価格'),
        null = True,
        blank = True
    )

    status = models.CharField(
        verbose_name = _('ステータス'),
        null = True,
        max_length = 50,
    )
    error_message = models.CharField(
        verbose_name = 'エラー内容',
        max_length = 50,
        default = None,
        null = True,
        blank = True
    )
    order_id = models.CharField(
        verbose_name = _('取引ID'),
        max_length = 50,
        null = True,
        blank = True
    )

    ordered_at = UnixTimeStampField(
        verbose_name = _('注文時刻unixtime'),
        use_numeric = True,
        null = True,
        auto_now_add = False,
        auto_now = False,
        blank = True
    )

    updated_at = UnixTimeStampField(
        verbose_name = _('更新日時unixtimestamp'), 
        use_numeric = True,  
        auto_now = True,
    )

class OrderRelation(models.Model):
    def __str__(self):
        return self.special_order

    class Meta:
        verbose_name = "発注一覧"
        verbose_name_plural = "発注一覧"
    
    PAIR = [
        'btc_jpy',
        'xrp_jpy',
        'ltc_btc',
        'eth_btc',
        'mona_jpy',
        'mona_btc',
        'bcc_jpy',
        'bcc_btc',
    ]
    SPECIAL_ORDER = [
        'SINGLE',
        # 'IFD',
        # 'OCO',
        # 'IFDOCO'  
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    pair = models.CharField(
        verbose_name = _('通貨'),
        max_length = 50,
    )
    
    special_order = models.CharField(
        verbose_name = _('特殊注文'), 
        max_length = 50,
    )

    order_1 = models.OneToOneField(
        BitbankOrder,
        verbose_name = '新規注文',
        related_name = 'new_order',
        null = True,
        blank = True,
        on_delete = models.CASCADE
    )
    order_2 = models.OneToOneField(
        BitbankOrder,
        verbose_name = '決済注文1',
        related_name = 'settle_order_1',
        null = True,
        blank = True,
        on_delete = models.CASCADE
    )
    order_3 = models.OneToOneField(
        BitbankOrder,
        verbose_name = '決済注文2',
        related_name = 'settle_order_2',
        null = True,
        blank = True,
        on_delete = models.CASCADE
    )
    placed_at = models.DateTimeField(
        verbose_name = '注文日時',
        auto_now_add = True
    )
    is_active = models.BooleanField(
        verbose_name = '有効',
        default = True,
    )

class Alert(models.Model):
    def __str__(self):
        return self.pair
    class Meta:
        verbose_name = "通知設定"
        verbose_name_plural = "通知設定"
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    pair = models.CharField(
        verbose_name = _('通貨'),
        max_length = 50,
        default = 'btc_jpy',
    )

    threshold = models.FloatField(
        verbose_name = _('通知レート'),
        null = False,
    )

    over_or_under = models.CharField(
        verbose_name = _('上下'),
        max_length = 50,
        null = False,
    )

    alerted_at = models.DateTimeField(
        verbose_name = _('通知日時'),   
        auto_now = False,
        null = True
    )

    is_active = models.BooleanField(
        verbose_name = _('有効'),
        null = True,
    )

class Attachment(models.Model):
    def __str__(self):
        return self.file.name
    class Meta:
        verbose_name = "添付ファイル"
        verbose_name_plural = "添付ファイル"
    file = models.FileField(
        verbose_name = 'ファイル',
        upload_to = 'attachments',
        null = False,
        blank = False,
    )
    uploaded_at = models.DateTimeField(
        verbose_name = 'アップロード日時',
        auto_now_add = True,
    )

class Inquiry(models.Model):
    def __str__(self):
        return self.subject
    class Meta:
        verbose_name = "問い合せ"
        verbose_name_plural = "問い合せ"

    user = models.ForeignKey(User, on_delete=models.CASCADE)

    subject = models.CharField(
        verbose_name = _('件名'),
        max_length = 255,
    )
    body = models.CharField(
        verbose_name = _('内容'),
        max_length = 255,
    )
    email_for_reply = models.EmailField(
        verbose_name = _('通知用メールアドレス'),
    )
    attachment_1 = models.ForeignKey(
        Attachment,
        verbose_name = '添付ファイル1',
        null = True,
        blank = True,
        on_delete = models.CASCADE,
        related_name = 'att_1'
    )
    attachment_2 = models.ForeignKey(
        Attachment,
        verbose_name = '添付ファイル2',
        null = True,
        blank = True, 
        on_delete = models.CASCADE,
        related_name = 'att_2'
    )
    attachment_3 = models.ForeignKey(
        Attachment,
        verbose_name = '添付ファイル3',
        null = True,
        blank = True,
        on_delete = models.CASCADE,
        related_name = 'att_3'
    )

    closed = models.BooleanField(
        _('解決済'),
        default=False,
    )
    date_initiated = models.DateTimeField(
        verbose_name = '問い合せ日時',
        auto_now_add = True,

    )

@receiver(post_delete, sender=Attachment)
def delete_file(sender, instance, **kwargs):
    instance.file.delete(False)
