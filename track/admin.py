from django.contrib import admin

from .models import Budget, Category, Expense


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "kind")
    search_fields = ("name",)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("date", "type", "amount", "category", "note", "user_id")
    list_filter = ("type", "category", "date")
    search_fields = ("note", "user_id")


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("category", "monthly_limit", "spent", "user_id")
    search_fields = ("user_id",)
