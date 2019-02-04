import json
import logging
import os

import python_bitbankcc
from django.core.management.base import BaseCommand
from django.utils import timezone

from ...models import Order, User, Alert


# BaseCommandを継承して作成
class Command(BaseCommand):
    # python manage.py help count_entryで表示されるメッセージ
    help = '逆指値、ストップリミット注文を出します'

    # コマンドライン引数を指定します。(argparseモジュール https://docs.python.org/2.7/library/argparse.html)
    # 今回はblog_idという名前で取得する。（引数は最低でも1個, int型）
    # def add_arguments(self, parser):
    #     parser.add_argument('user_pk', nargs='+', type=int)

    # コマンドが実行された際に呼ばれるメソッド
    def handle(self, *args, **options):
        logger = logging.getLogger('batch_logger')
        for i in range(10):
            logger.info('started')
            pub = python_bitbankcc.public()
            for user in User.objects.all():
                # API KEYが登録されているユーザのみ処理
                if user.api_key != "" or user.api_secret_key != "":
                    # キー情報セット
                    try:
                        prv = python_bitbankcc.private(user.api_key, user.api_secret_key)
                    except Exception as e:
                        logger.error('User:' + user.email + ' Message: ' + str(e.args))
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
                        try:
                            alerts_by_pair = Alert.objects.filter(pair=pair).filter(is_active=True)
                            for alert in alerts_by_pair:
                                if (alert.over_or_under == '以上' and float(ticker_dict.get('buy')) >= alert.threshold) or \
                                    (alert.over_or_under == '以上' and float(ticker_dict.get('buy')) >= alert.threshold):
                                    context = { "user": user, "ticker_dict": ticker_dict, "pair": pair }
                                    subject = get_template('bitbank/mail_template/rate_notice/subject.txt').render(context)
                                    message = get_template('bitbank/mail_template/rate_notice/message.txt').render(context)
                                    user.email_user(subject, message)
                                    logger.info('rate notice sent to:' + user.email_for_notice)
                        except Exception as e:
                            logger.error('user:' + user.email + ' pair:' + pair + ' alert:' + alert.pk + ' error:' + str(e.args))

                        # 逆指値の注文取得
                        stop_market_orders_by_pair = Order.objects.filter(pair=pair).filter(order_type='逆指値').filter(order_id__isnull=True)
                        
                        # 各注文を処理
                        for stop_market_order in stop_market_orders_by_pair:
                            # 売りの場合
                            if (stop_market_order.side == 'sell' and float(ticker_dict.get('sell')) <= stop_market_order.price_for_stop) or \
                                (stop_market_order.side == 'buy' and float(ticker_dict.get('buy')) >= stop_market_order.price_for_stop):
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
                                    logger.error('user:' + user.email + 'pair:' + pair + ' pk:' + stop_market_order.pk + ' error: ' +  str(e.args))
                                    continue

                        # ストップリミットの注文取得
                        stop_limit_orders_by_pair = Order.objects.filter(pair=pair).filter(order_type='ストップリミット').filter(order_id__isnull=True)
                        
                        # 各注文を処理
                        for stop_limit_order in stop_limit_orders_by_pair:
                            if (stop_limit_order.side == 'sell' and ticker_dict.get('sell') <= stop_limit_order.price_for_stop) or \
                                (stop_limit_order.side == 'buy' and ticker_dict.get('buy') >= stop_limit_order.price_for_stop):
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
                                    logger.error('user:' + user.email + 'pair:' + pair + ' pk:' + stop_market_order.pk + ' error: ' +  str(e.args))
                                    continue
            logger.info('completed')
