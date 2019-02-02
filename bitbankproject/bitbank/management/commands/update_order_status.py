from django.core.management.base import BaseCommand
from ...models import Order, User
import os, json, python_bitbankcc
import logging


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
        logger = logging.getLogger('command')
        logger.info('update_order_status started')
        for user in User.objects.all():
            # API KEYが登録されているユーザのみ処理
            if user.api_key != "" or user.api_secret_key != "":
                # キー情報セット
                try:
                    prv = python_bitbankcc.private(user.api_key, user.api_secret_key)
                except Exception as e:
                    logger.error('User:'user.email + ' Message: ' e.args)
                    continue

                # 通貨ペアをイテレーション
                for seq, pair in enumerate(Order.PAIR):
                    orders_by_pair = Order.objects.filter(pair=pair[0]).filter(status__in=['UNFILLED', 'PARTIALLY_FILLED']).exclude(order_id__isnull=True).values_list('order_id', flat=True)
                    # オーダが存在する通貨のみ処理
                
                    if orders_by_pair.count() != 0:
                        try:
                            ret = prv.get_orders_info(
                                pair[0], # ペア
                                list(orders_by_pair) # 注文IDのリスト
                            )
                        except Exception as e:
                            logger.error('User:'user.email + ' Pair: ' + pair[0] + ' Order ids: ' + list(orders_by_pair) + ' Message: ' e.args)
                            continue

                        for order_dict in ret.get('orders'):
                            order_id = order_dict.get('order_id')
                            remaining_amount = order_dict.get('remaining_amount')
                            executed_amount = order_dict.get('executed_amount')
                            average_price = order_dict.get('average_price')
                            status = order_dict.get('status')
                            # 約定通知がONのユーザで約定があった場合
                            if status == 'FILLED' and user.notify_if_filled == 'ON':
                                # 約定通知メール
                                context = Context({"user": user, "order_dict": order_dict})
                                subject_template = get_template('bitbank/mail_template/fill_notice/subject.txt')
                                subject = subject_template.render(context)
                                message_template = get_template('bitbank/mail_template/fill_notice/message.txt')
                                message = message_template.render(context)
                                user.email_user(subject, message)
                            subj_order = Order.objects.filter(order_id=order_id).get()
                            subj_order.remaining_amount = remaining_amount
                            subj_order.executed_amount = executed_amount
                            subj_order.average_price = average_price
                            subj_order.status = status
                            subj_order.save()
        logger.info('update_order_status completed')
                            
                # for order in Order.objects.filter(pair = pair(0)):
                #     message = ""
                #     message += 'side: ' + order.side
                #     message += 'user: ' + order.user.email
                    
                #     self.stdout.write(self.style.SUCCESS(message))