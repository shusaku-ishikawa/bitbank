import json
import logging
import os
from datetime import datetime
import time
import python_bitbankcc
from django.core.management.base import BaseCommand
from django.template.loader import get_template

from .models import OrderRelation, BitbankOrder, User



# BaseCommandを継承して作成
logger = logging.getLogger('batch_logger')

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
        order_obj.status = ret.get('status')
        order_obj.save()
        return True
    except:
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
        order_obj.order_id = ret.get('order_id')
        order_obj.save()
        return True
    except Exception as e:
        order_obj.status = BitbankOrder.STATUS_FAILED_TO_ORDER
        order_obj.error_message = str(e.args)
        order_obj.save()
        return False
