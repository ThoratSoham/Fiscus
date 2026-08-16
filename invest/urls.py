from django.urls import path

from . import views

urlpatterns = [
    path("api/invest/instruments/", views.instruments, name="invest-instruments"),
    path("api/invest/portfolio/", views.portfolio, name="invest-portfolio"),
    path("api/invest/chart/<int:pk>/", views.chart_data, name="invest-chart"),
    path("api/invest/orders/", views.place_order, name="invest-orders"),
    path("api/invest/orders/list/", views.order_list, name="invest-order-list"),
    path("api/invest/orders/<int:pk>/cancel/", views.cancel_order, name="invest-order-cancel"),
    path("api/invest/reset/", views.reset_portfolio, name="invest-reset"),
    path("invest/", views.invest_page, name="invest-page"),
]
