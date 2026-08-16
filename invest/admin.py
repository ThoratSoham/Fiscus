from django.contrib import admin

from .models import Holding, Instrument, Order, VirtualPortfolio


@admin.register(Instrument)
class InstrumentAdmin(admin.ModelAdmin):
    list_display = ("symbol", "name", "kind", "base_price", "volatility", "drift", "is_active")
    search_fields = ("symbol", "name")
    list_filter = ("kind", "is_active")


@admin.register(VirtualPortfolio)
class VirtualPortfolioAdmin(admin.ModelAdmin):
    list_display = ("name", "user_id", "seed", "starting_balance", "current_balance", "created_at")
    search_fields = ("user_id", "name")


@admin.register(Holding)
class HoldingAdmin(admin.ModelAdmin):
    list_display = ("portfolio", "instrument", "quantity", "avg_price", "created_at")
    search_fields = ("instrument__symbol",)
    autocomplete_fields = ("instrument",)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("user_id", "side", "instrument", "quantity", "order_type", "status", "price", "created_at")
    search_fields = ("user_id", "instrument__symbol")
    list_filter = ("side", "order_type", "status")
