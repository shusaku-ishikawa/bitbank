import json
import logging
import os
import time 
import python_bitbankcc
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.template.loader import get_template

from ...models import Order, User, Alert


# BaseCommandを継承して作成
class Command(BaseCommand):
    # python manage.py help count_entryで表示されるメッセージ
    help = '逆指値、ストップリミット注文を出します'

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
            pub = python_bitbankcc.public()
            for user in User.objects.all():
                # API KEYが登録されているユーザのみ処理
                if user.api_key == "" or user.api_secret_key == "":
                    logger.info('user:' + user.email + ' message: ' + ' keys not registered')
                    continue

                # キー情報セット
                try:
                    prv = python_bitbankcc.private(user.api_key, user.api_secret_key)
                except Exception as e:
                    logger.error('user:' + user.email + ' message: ' + str(e.args))
                    continue

                # 通貨ペアをイテレーション
                for pair in Order.PAIR:
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
                                context = { "user": user, "ticker_dict": ticker_dict, "pair": pair }
                                subject = get_template('bitbank/mail_template/rate_notice/subject.txt').render(context)
                                message = get_template('bitbank/mail_template/rate_notice/message.txt').render(context)
                                user.email_user(subject, message)
                                logger.info('rate notice sent to:' + user.email_for_notice)
                                alert.is_active = False
                                alert.alerted_at = timezone.now()
                                alert.save()
                        except Exception as e:
                            alert.is_active = False
                            alert.save()
                            logger.error('user:' + user.email + ' pair:' + pair + ' alert:' + str(alert.pk) + ' error:' + str(e.args))

                    # 逆指値の注文取得
                    stop_market_orders_by_pair = Order.objects.filter(pair=pair).filter(order_type=Order.TYPE_STOP_MARKET).filter(order_id__isnull=True).filter(status__in=[Order.STATUS_READY_TO_ORDER])
                    
                    # 各注文を処理
                    for stop_market_order in stop_market_orders_by_pair:
                        # 売りの場合
                        logger.info('Stop market order found. side:' + stop_market_order.side + ' stop price:' + str(stop_market_order.price_for_stop) + ' market sell:' + ticker_dict.get('sell') + ' market buy:' + ticker_dict.get('buy'))
                        if (stop_market_order.side == 'sell' and (float(ticker_dict.get('sell')) <= stop_market_order.price_for_stop)) or \
                            (stop_market_order.side == 'buy' and (float(ticker_dict.get('buy')) >= stop_market_order.price_for_stop)):
                            # 成行で売り注文
                            try:
                                res_dict = prv.order(
                                    pair, # ペア
                                    stop_market_order.price, # 価格
                                    stop_market_order.start_amount, # 注文枚数
                                    stop_market_order.side, # 注文サイド
                                    'market' # 注文タイプ
                                )
                                stop_market_order.order_id = res_dict.get('order_id')
                                stop_market_order.ordered_at = res_dict.get('ordered_at')
                                stop_market_order.status = res_dict.get('status')     
                                stop_market_order.save() 
                            except Exception as e:
                                stop_market_order.status = Order.STATUS_FAILED_TO_ORDER
                                stop_market_order.save()
                                logger.error('user:' + user.email + 'pair:' + pair + ' pk:' + str(stop_market_order.pk) + ' error: ' +  str(e.args))
                                continue

                    # ストップリミットの注文取得
                    stop_limit_orders_by_pair = Order.objects.filter(pair=pair).filter(order_type=Order.TYPE_STOP_LIMIT).filter(order_id__isnull=True).filter(status__in=[Order.STATUS_READY_TO_ORDER])
                    
                    # 各注文を処理
                    for stop_limit_order in stop_limit_orders_by_pair:
                        logger.info('Stop limit order found. side:' + stop_limit_order.side + ' stop price:' + str(stop_limit_order.price_for_stop) + ' market sell:' + ticker_dict.get('sell') + ' market buy:' + ticker_dict.get('buy'))
                        
                        if (stop_limit_order.side == 'sell' and (float(ticker_dict.get('sell')) <= stop_limit_order.price_for_stop)) or \
                            (stop_limit_order.side == 'buy' and (float(ticker_dict.get('buy')) >= stop_limit_order.price_for_stop)):
                            try:
                                res_dict = prv.order(
                                    pair, # ペア
                                    stop_limit_order.price, # 価格
                                    stop_limit_order.start_amount, # 注文枚数
                                    stop_limit_order.side, # 注文サイド
                                    'limit' # 注文タイプ
                                )
                                stop_limit_order.order_id = res_dict.get('order_id')
                                stop_limit_order.ordered_at = res_dict.get('ordered_at')
                                stop_limit_order.status = res_dict.get('status')
                                stop_limit_order.save()
                            except:
                                stop_limit_order.status = Order.STATUS_FAILED_TO_ORDER
                                stop_limit_order.save()
                                logger.error('user:' + user.email + 'pair:' + pair + ' pk:' + str(stop_market_order.pk) + ' error: ' +  str(e.args))
                                continue
        logger.info('completed')  
          
