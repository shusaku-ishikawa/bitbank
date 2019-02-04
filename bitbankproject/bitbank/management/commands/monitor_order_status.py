import json
import logging
import os
from datetime import datetime

import python_bitbankcc
from django.core.management.base import BaseCommand
from django.template.loader import get_template

from ...models import Order, User


# BaseCommandを継承して作成
class Command(BaseCommand):
    # python manage.py help count_entryで表示されるメッセージ
    help = 'Update orders'
    

    # コマンドライン引数を指定します。(argparseモジュール https://docs.python.org/2.7/library/argparse.html)
    # 今回はblog_idという名前で取得する。（引数は最低でも1個, int型）
    # def add_arguments(self, parser):
    #     parser.add_argument('user_pk', nargs='+', type=int)

    # コマンドが実行された際に呼ばれるメソッド
    def handle(self, *args, **options):
        logger = logging.getLogger('batch_logger')
        for i in range(25):
            logger.info("started")
            for user in User.objects.all():
                # API KEYが登録されているユーザのみ処理
                if user.api_key != "" or user.api_secret_key != "":
                    # キー情報セット
                    try:
                        prv = python_bitbankcc.private(user.api_key, user.api_secret_key)
                    except Exception as e:
                        logger.error('User:' + user.email + ' Message: ' +  e.args)
                        continue

                    # 通貨ペアをイテレーション
                    for pair in Order.PAIR:
                        orders_by_pair = Order.objects.filter(pair=pair).filter(status__in=['UNFILLED', 'PARTIALLY_FILLED']).exclude(order_id__isnull=True).values_list('order_id', flat=True)
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
                                    if status == 'FULLY_FILLED' and user.notify_if_filled == 'ON':
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
