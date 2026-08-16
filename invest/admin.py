from django.contrib import admin

from .models import Holding, VirtualPortfolio


@admin.register(VirtualPortfolio)
class VirtualPortfolioAdmin(admin.ModelAdmin):
    list_display = ("name", "user_id", "created_at")
    search_fields = ("user_id", "name")


@admin.register(Holding)
class HoldingAdmin(admin.ModelAdmin):
    list_display = ("portfolio", "symbol", "quantity", "avg_price", "created_at")
    search_fields = ("symbol",)
