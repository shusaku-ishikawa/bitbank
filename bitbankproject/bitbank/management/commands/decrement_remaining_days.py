import logging
import os
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.template.loader import get_template
from datetime import datetime, timedelta
from ...models import User


# BaseCommandを継承して作成
class Command(BaseCommand):
    # python manage.py help count_entryで表示されるメッセージ
    help = '残り日数を１減らします。'

    # コマンドが実行された際に呼ばれるメソッド
    def handle(self, *args, **options):
        alert_if = 5 # days

        active_customers = User.objects.filter(is_staff = False).filter(is_superuser = False).filter(is_active = True)

        for customer in active_customers:
            new_remaning_days = customer.remaining_days - 1
            customer.remaining_days = new_remaning_days

            if new_remaning_days <= 0:
                customer.is_active = False 
            customer.save()
            
            context = {
                'customer': customer,
            }

            if new_remaning_days == alert_if:
                subject = get_template('bitbank/mail_template/expiry_precaution/subject.txt').render(context)
                message = get_template('bitbank/mail_template/expiry_precaution/message.txt').render(context)
                customer.email_user(subject, message)

            elif new_remaning_days <= 0:
                subject = get_template('bitbank/mail_template/expiry_notification/subject.txt').render(context)
                message = get_template('bitbank/mail_template/expiry_notification/message.txt').render(context)
                customer.email_user(subject, message)
            