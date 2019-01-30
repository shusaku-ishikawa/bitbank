# Generated by Django 2.1.5 on 2019-01-30 05:25

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bitbank', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='order_type',
            field=models.CharField(choices=[('成行', '成行'), ('指値', '指値'), ('逆指値', '逆指値'), ('ストップリミット', 'ストップリミット')], default='成行', max_length=50, verbose_name='注文方法'),
        ),
        migrations.AlterField(
            model_name='order',
            name='pair',
            field=models.CharField(choices=[('btc_jpy', 'btc_jpy'), ('xrp_jpy', 'xrp_jpy'), ('ltc_btc', 'ltc_btc'), ('eth_btc', 'eth_btc'), ('mona_jpy', 'mona_jpy'), ('mona_btc', 'mona_btc'), ('bcc_jpy', 'bcc_jpy'), ('bcc_btc', 'bcc_btc')], default='btc_jpy', max_length=50, verbose_name='通貨'),
        ),
        migrations.AlterField(
            model_name='order',
            name='special_order',
            field=models.CharField(choices=[('SINGLE', 'SINGLE'), ('IFD', 'IFD'), ('OCO', 'OCO'), ('IFDOCO', 'IFDOCO')], default='SINGLE', max_length=50, verbose_name='特殊注文'),
        ),
    ]
