# Generated by Django 2.1.5 on 2019-02-23 11:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bitbank', '0002_auto_20190222_2139'),
    ]

    operations = [
        migrations.AddField(
            model_name='bitbankorder',
            name='error_message',
            field=models.CharField(blank=True, default=None, max_length=50, null=True, verbose_name='エラー内容'),
        ),
    ]
