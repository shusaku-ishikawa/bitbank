import json
import logging
import os
import time 
import python_bitbankcc
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.template.loader import get_template

from ...models import OrderRelation,BitbankOrder, User, Alert
from ... import _util

# BaseCommandを継承して作成
class Command(BaseCommand):
    # python manage.py help count_entryで表示されるメッセージ
    help = '逆指値、ストップリミット注文を出します'

    # コマンドが実行された際に呼ばれるメソッド
    def handle(self, *args, **options):
        logger = logging.getLogger('batch_logger')
        #logger.info('started')
        time_started = time.time()
        n = 0
        while True:
            time.sleep(1)
            n = n + 1
            time_elapsed = time.time() - time_started
            if time_elapsed > 57.0:
                break;
            pub = python_bitbankcc.public()
            for user in User.objects.all():
                # API KEYが登録されているユーザのみ処理
                if user.api_key == "" or user.api_secret_key == "":
                    continue

                # キー情報セット
                try:
                    prv = python_bitbankcc.private(user.api_key, user.api_secret_key)
                except Exception as e:
                    logger.error('user:' + user.email + ' message: ' + str(e.args))
                    continue

                # 通貨ペアをイテレーション
                for pair in OrderRelation.PAIR:
                    
                    # Tickerの取得
                    try:
                        ticker_dict = pub.get_ticker(pair)
                    except Exception as e:
                        logger.error('user:' + user.email + ' pair:' + pair + ' error:' + str(e.args))
                        continue
                    
                    # 通知処理
                    alerts_by_pair = Alert.objects.filter(pair=pair).filter(is_active=True)

                    for alert in alerts_by_pair:
                        try:
                            if (alert.over_or_under == '以上' and float(ticker_dict.get('last')) >= alert.threshold) or \
                                (alert.over_or_under == '以上' and float(ticker_dict.get('last')) >= alert.threshold):

                                if user.use_alert == 'ON':
                                    context = { "user": user, "ticker_dict": ticker_dict, "pair": pair }
                                    subject = get_template('bitbank/mail_template/rate_notice/subject.txt').render(context)
                                    message = get_template('bitbank/mail_template/rate_notice/message.txt').render(context)
                                    user.email_user(subject, message)
                                    #logger.info('rate notice sent to:' + user.email_for_notice)
                                    alert.alerted_at = timezone.now()
                                    
                                alert.is_active = False
                                alert.save()
                        except Exception as e:
                            alert.is_active = False
                            alert.save()
                            logger.error('user:' + user.email + ' pair:' + pair + ' alert:' + str(alert.pk) + ' error:' + str(e.args))

                    # 逆指値の注文取得
                    stop_market_orders_by_pair = BitbankOrder.objects.filter(user=user).filter(pair=pair).filter(order_type=BitbankOrder.TYPE_STOP_MARKET).filter(order_id__isnull=True).filter(status__in=[BitbankOrder.STATUS_READY_TO_ORDER])
                    
                    # 各注文を処理
                    for stop_market_order in stop_market_orders_by_pair:
                        # 売りの場合
                        logger.info('Stop market order found. side:' + stop_market_order.side + ' stop price:' + str(stop_market_order.price_for_stop) + ' market sell:' + ticker_dict.get('sell') + ' market buy:' + ticker_dict.get('buy'))
                        if (stop_market_order.side == 'sell' and (float(ticker_dict.get('sell')) <= stop_market_order.price_for_stop)) or \
                            (stop_market_order.side == 'buy' and (float(ticker_dict.get('buy')) >= stop_market_order.price_for_stop)):
                            _util.place_order(prv, stop_market_order)

                    # ストップリミットの注文取得
                    stop_limit_orders_by_pair = BitbankOrder.objects.filter(user=user).filter(pair=pair).filter(order_type=BitbankOrder.TYPE_STOP_LIMIT).filter(order_id__isnull=True).filter(status__in=[BitbankOrder.STATUS_READY_TO_ORDER])
                    
                    # 各注文を処理
                    for stop_limit_order in stop_limit_orders_by_pair:
                        logger.info('Stop limit order found. side:' + stop_limit_order.side + ' stop price:' + str(stop_limit_order.price_for_stop) + ' market sell:' + ticker_dict.get('sell') + ' market buy:' + ticker_dict.get('buy'))
                        
                        if (stop_limit_order.side == 'sell' and (float(ticker_dict.get('sell')) <= stop_limit_order.price_for_stop)) or \
                            (stop_limit_order.side == 'buy' and (float(ticker_dict.get('buy')) >= stop_limit_order.price_for_stop)):
                            _util.place_order(prv, stop_limit_order)
        logger.info('completed')  
          
