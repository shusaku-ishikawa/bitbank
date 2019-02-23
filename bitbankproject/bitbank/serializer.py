from rest_framework import serializers
from .models import OrderRelation, BitbankOrder




class BitbankOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = BitbankOrder
        fields = ('pk', 'pair', 'side', 'order_type', 'price', 'price_for_stop', 'start_amount', 'remaining_amount', 'executed_amount', 'average_price', 'status', 'order_id', 'ordered_at', 'error_message')

class OrderSerializer(serializers.ModelSerializer):
    order_1 = BitbankOrderSerializer(many = False, read_only = True)
    order_2 = BitbankOrderSerializer(many = False, read_only = True)
    order_3 = BitbankOrderSerializer(many = False, read_only = True)
    
    class Meta:
        model = OrderRelation
        fields = ('pk', 'pair', 'special_order', 'order_1', 'order_2', 'order_3', 'placed_at', 'is_active')