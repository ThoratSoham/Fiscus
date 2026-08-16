from rest_framework import serializers

from .models import Budget, Category, Expense


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "kind"]


class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Expense
        fields = ["id", "amount", "category", "category_name", "type", "date", "note", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value


class BudgetSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Budget
        fields = ["id", "category", "category_name", "monthly_limit", "spent"]
        read_only_fields = ["id", "spent"]  # spent is recomputed server-side

    def validate_monthly_limit(self, value):
        if value <= 0:
            raise serializers.ValidationError("Monthly limit must be greater than zero.")
        return value
