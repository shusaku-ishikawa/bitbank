import json
import logging
import os
from datetime import datetime
import time
import python_bitbankcc
from django.core.management.base import BaseCommand
from django.template.loader import get_template

from ...models import Order, BitbankOrder, User


# BaseCommandを継承して作成
def notify_user(user, order_obj):
    readable_datetime = datetime.fromtimestamp(int(int(order_obj.ordered_at) / 1000))
    context = { "user": user, "order": order_obj, 'readable_datetime': readable_datetime }
    subject = get_template('bitbank/mail_template/fill_notice/subject.txt').render(context)
    message = get_template('bitbank/mail_template/fill_notice/message.txt').render(context)
    user.email_user(subject, message)
    logger.info('notice sent to:' + user.email_for_notice)

def get_status(prv, order_obj):
    ret = prv.get_order(
        order_obj.pair, 
        order_obj.order_id
    )
    order_obj.remaining_amount = ret.get('remaining_amount')
    order_obj.executed_amount = ret.get('executed_amount')
    order_obj.average_price = ret.get('average_price')
    status = ret.get('status')
    order_obj.status = status
    order_obj.save()
    return status

def cancel_order(prv, order_obj):
    try:
        ret = prv.cancel_order(
            order_obj.pair, # ペア
            order_obj.order_id # 注文ID
        )
        order_obj.remaining_amount = ret.get('remaining_amount')
        order_obj.executed_amount = ret.get('executed_amount')
        order_obj.average_price = ret.get('average_price')
        order_obj.status = status
        order_obj.save()
        return True
    except Exception as e:
        return False

def place_order(prv, order_obj):
    try:
        ret = prv.order(
            order_obj.pair, # ペア
            order_obj.price, # 価格
            order_obj.start_amount, # 注文枚数
            order_obj.side, # 注文サイド
            'market' if order_obj.order_type.find("market") > -1 else 'limit' # 注文タイプ
        )
        order_obj.remaining_amount = ret.get('remaining_amount')
        order_obj.executed_amount = ret.get('executed_amount')
        order_obj.average_price = ret.get('average_price')
        order_obj.status = ret.get('status')
        order_obj.ordered_at = ret.get('ordered_at')
        order_obj.save()
    except Exception as e:
        order_obj.status = BitbankOrder.STATUS_FAILED_TO_ORDER
        order_obj.save()


class Command(BaseCommand):
    # python manage.py help count_entryで表示されるメッセージ
    help = '注文のステータスを更新します'
    # コマンドが実行された際に呼ばれるメソッド
    def handle(self, *args, **options):
        logger = logging.getLogger('batch_logger')
        logger.info('started')
        time_started = time.time()
        n = 0
        while True:
            time.sleep(1)
            n = n + 1
            time_elapsed = time.time() - time_started
            if time_elapsed > 57.0:
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
                active_orders = Order.objects.filter(is_active=True)
                logger.info(str(active_orders))
                for order in active_orders:
                    o_1 = order.order_1
                    o_2 = order.order_2
                    o_3 = order.order_3

                    # Order#1が存在し、未約定の場合
                    if o_1 != None and o_1.status in {BitbankOrder.STATUS_UNFILLED, BitbankOrder.STATUS_PARTIALLY_FILLED}:
                        status = get_status(prv, o_1)
                        logger.info('o_1 found ' + str(o_1.order_id) + ' status:' + status)

                        if status == BitbankOrder.STATUS_FULLY_FILLED: 
                            if o_2 != None:
                                place_order(prv, order.pair, o_2)
            
                            if o_3 != None:
                                place_order(prv, order.pair, o_3)

                            if user.notify_if_filled == 'ON':
                                # 約定通知メール
                                notify_user(user, order.pair, o_1)

                    if o_2 != None and o_2.status in {BitbankOrder.STATUS_UNFILLED, BitbankOrder.STATUS_PARTIALLY_FILLED}:
                        status = get_status(prv, o_2)
                        if status  == BitbankOrder.STATUS_FULLY_FILLED:
                            # order_3のキャンセル
                            cancel_order(prv, o_3)
                            if user.notify_if_filled == 'ON':
                                # 約定通知メール
                                notify_user(user, order.pair, o_2)
                    if o_3 != None and o_3.status in {BitbankOrder.STATUS_UNFILLED, BitbankOrder.STATUS_PARTIALLY_FILLED}:
                        status = get_status(prv, o_3)
                        if status  == BitbankOrder.STATUS_FULLY_FILLED:
                            # order_2のキャンセル
                            cancel_order(prv, o_2)
                            if user.notify_if_filled == 'ON':
                                # 約定通知メール
                                notify_user(user, o_3)
                    if (o_1 == None or o_1.status in {BitbankOrder.STATUS_FULLY_FILLED, BitbankOrder.STATUS_CANCELED_UNFILLED, BitbankOrder.STATUS_CANCELED_PARTIALLY_FILLED, BitbankOrder.STATUS_FAILED_TO_ORDER}) \
                        and (o_2 == None or o_2.status in {BitbankOrder.STATUS_FULLY_FILLED, BitbankOrder.STATUS_CANCELED_UNFILLED, BitbankOrder.STATUS_CANCELED_PARTIALLY_FILLED, BitbankOrder.STATUS_FAILED_TO_ORDER}) \
                        and (o_3 == None or o_3.status in {BitbankOrder.STATUS_FULLY_FILLED, BitbankOrder.STATUS_CANCELED_UNFILLED, BitbankOrder.STATUS_CANCELED_PARTIALLY_FILLED, BitbankOrder.STATUS_FAILED_TO_ORDER}):
                        order.is_active = False

                    order.save()

                             
                    




        logger.info('completed')
