

from django.contrib import admin
from django.urls import path, include
from rest_framework import routers

from .routers import CustomReadOnlyRouter
from .views import get_reports, SaleViewSet, SupplyViewSet

urlpatterns = [
    path('reports', get_reports),
    path('sales', SaleViewSet.as_view(actions={
        'get': 'list',
        'post': 'create'
    })),
    path('supplies', SupplyViewSet.as_view(actions={
        'get': 'list',
        'post': 'create'
    })),
    path('sales/<int:pk>', SaleViewSet.as_view(actions={
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    })),
    path('supplies/<int:pk>', SupplyViewSet.as_view(actions={
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy'
    })),
]
