# Generated by Django 2.1.5 on 2019-02-27 12:47

from django.db import migrations
import unixtimestampfield.fields


class Migration(migrations.Migration):

    dependencies = [
        ('bitbank', '0002_auto_20190227_2036'),
    ]

    operations = [
        migrations.AlterField(
            model_name='bitbankorder',
            name='updated_at',
            field=unixtimestampfield.fields.UnixTimeStampField(auto_now=True, verbose_name='更新日時unixtimestamp'),
        ),
    ]