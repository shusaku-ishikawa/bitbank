from django.core.management.base import BaseCommand
from ...models import Order, User
import os, json, python_bitbankcc


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
        for user in User.objects.all():
            for seq, pair in enumerate(Order.PAIR):
                self.stdout.write(self.style.SUCCESS(pair[0]))
                orders_by_pair = Order.objects.filter(pair=pair[0]).exclude(order_id__isnull=True).values_list('order_id', flat=True)
                if orders_by_pair.count() != 0:
                    self.stdout.write(str(list(orders_by_pair)))
                # for order in Order.objects.filter(pair = pair(0)):
                #     message = ""
                #     message += 'side: ' + order.side
                #     message += 'user: ' + order.user.email
                    
                #     self.stdout.write(self.style.SUCCESS(message))