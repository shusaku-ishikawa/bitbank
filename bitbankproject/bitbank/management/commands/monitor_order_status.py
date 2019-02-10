import json
import logging
import os
from datetime import datetime
import time
import python_bitbankcc
from django.core.management.base import BaseCommand
from django.template.loader import get_template

from ...models import Order, User


# BaseCommandを継承して作成
class Command(BaseCommand):
    # python manage.py help count_entryで表示されるメッセージ
    help = '注文のステータスを更新します'
    # コマンドが実行された際に呼ばれるメソッド
    def handle(self, *args, **options):
        logger = logging.getLogger('batch_logger')
        logger.info('started')
        time_started = time.clock()
        n = 0
        while True:
            n = n + 1
            time_elapsed = time.clock() - time_started
            logger.info(str(n) + 's time. ' + str(time_elapsed) + ' has elapsed')
            if time_elapsed > 55.0:
                break;
            for user in User.objects.all():
                # API KEYが登録されているユーザのみ処理
                if user.api_key != "" or user.api_secret_key != "":
                    # キー情報セット
                    try:
                        prv = python_bitbankcc.private(user.api_key, user.api_secret_key)
                    except Exception as e:
                        logger.error('user:' + user.email + ' message: ' +  str(e.args))
                        continue

                    # 通貨ペアをイテレーション
                    for pair in Order.PAIR:
                        orders_by_pair = Order.objects.filter(pair=pair).filter(status__in=[Order.STATUS_UNFILLED, Order.STATUS_PARTIALLY_FILLED]).exclude(order_id__isnull=True).values_list('order_id', flat=True)
                        # オーダが存在する通貨のみ処理
                    
                        if orders_by_pair.count() != 0:
                            try:
                                ret = prv.get_orders_info(
                                    pair, # ペア
                                    list(orders_by_pair) # 注文IDのリスト
                                )
                            except Exception as e:
                                logger.error('user:' + user.email + ' pair: ' + pair + ' order id: ' + str(orders_by_pair) + ' error: ' + str(e.args))
                                continue

                            for order_dict in ret.get('orders'):
                                try:
                                    order_id = order_dict.get('order_id')
                                    remaining_amount = order_dict.get('remaining_amount')
                                    executed_amount = order_dict.get('executed_amount')
                                    average_price = order_dict.get('average_price')
                                    status = order_dict.get('status')
                                    # 約定通知がONのユーザで約定があった場合
                                    if status == Order.STATUS_FULLY_FILLED and user.notify_if_filled == 'ON':
                                        # 約定通知メール
                                        readable_datetime = datetime.fromtimestamp(int(int(order_dict['ordered_at']) / 1000))
                                        context = { "user": user, "order_dict": order_dict, 'readable_datetime': readable_datetime }
                                        subject = get_template('bitbank/mail_template/fill_notice/subject.txt').render(context)
                                        message = get_template('bitbank/mail_template/fill_notice/message.txt').render(context)
                                        user.email_user(subject, message)
                                        logger.info('notice sent to:' + user.email_for_notice)
                                    subj_order = Order.objects.filter(order_id=order_id).get()
                                    subj_order.remaining_amount = remaining_amount
                                    subj_order.executed_amount = executed_amount
                                    subj_order.average_price = average_price
                                    subj_order.status = status
                                    subj_order.save()
                                except Exception as e:
                                    logger.error('user:' + user.email + ' pair:' + pair + ' order id: ' + str(orders_by_pair) + ' error: ' + str(e.args))
        logger.info('completed')
