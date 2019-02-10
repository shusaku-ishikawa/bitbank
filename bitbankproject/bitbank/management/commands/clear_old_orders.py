import logging
import os
from django.utils import timezone
from django.core.management.base import BaseCommand
from django.template.loader import get_template
from datetime import datetime, timedelta
from ...models import Order, User


# BaseCommandを継承して作成
class Command(BaseCommand):
    # python manage.py help count_entryで表示されるメッセージ
    help = '過去の約定済みデータを削除します'

    # コマンドが実行された際に呼ばれるメソッド
    def handle(self, *args, **options):
        logger = logging.getLogger('batch_logger')
        logger.info('started')
        delta_day = 180

        delete_if_older_than = timezone.now() - timedelta(days=delta_day)
        
        orders_to_delete = Order.objects.filter(status__in=[Order.STATUS_FULLY_FILLED, Order.STATUS_CANCELED_UNFILLED, Order.STATUS_CANCELED_PARTIALLY_FILLED, Order.STATUS_FAILED_TO_ORDER]).filter(updated_at__lte=delete_if_older_than)
        logger.info(str(orders_to_delete.count()) + ' will be deleted.')
        try:
            orders_to_delete.delete()
        except Exception as e:
            logger.error(str(e.args))
        logger.info('completed')
