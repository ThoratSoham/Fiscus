from rest_framework import serializers

from .models import Instrument, Order


class InstrumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Instrument
        fields = ["id", "symbol", "name", "kind", "base_price", "volatility", "drift", "is_active"]


class OrderSerializer(serializers.ModelSerializer):
    instrument_symbol = serializers.CharField(source="instrument.symbol", read_only=True)
    instrument_name = serializers.CharField(source="instrument.name", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "instrument",
            "instrument_symbol",
            "instrument_name",
            "side",
            "quantity",
            "order_type",
            "status",
            "trigger_price",
            "price",
            "note",
            "created_at",
            "filled_at",
        ]
        read_only_fields = [
            "id",
            "instrument_symbol",
            "instrument_name",
            "order_type",
            "status",
            "trigger_price",
            "price",
            "created_at",
            "filled_at",
        ]

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than zero.")
        return value
