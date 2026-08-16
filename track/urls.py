from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("expenses", views.ExpenseViewSet, basename="expense")
router.register("budgets", views.BudgetViewSet, basename="budget")

urlpatterns = [
    path("api/", include(router.urls)),
    path("api/categories/", views.CategoryListView.as_view(), name="category-list"),
    path("api/dashboard/", views.dashboard, name="dashboard-api"),
    path("dashboard/", views.dashboard_page, name="dashboard"),
]
