from rest_framework import serializers
from .models import Sale, Supply


class SaleSerializer(serializers.ModelSerializer):
    sale_time = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S')

    class Meta:
        model = Sale
        fields = [
            'id',
            'barcode',
            'quantity',
            'price',
            'sale_time',
        ]
        read_only_fields = ['id']


class SupplySerializer(serializers.ModelSerializer):
    supply_time = serializers.DateTimeField(format='%Y-%m-%d %H:%M:%S')

    class Meta:
        model = Supply
        fields = [
            'id',
            'barcode',
            'quantity',
            'price',
            'supply_time',
        ]
        read_only_fields = ['id']


class SaleUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sale
        fields = ['sale_time', 'quantity', 'price']


class SupplyUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supply
        fields = ['supply_time', 'quantity', 'price']
