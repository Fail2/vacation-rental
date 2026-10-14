from django.urls import path
from . import views

app_name = 'property_app'

urlpatterns = [
    path('', views.homepage_view, name='homepage'),
    path('search/', views.property_search_view, name='property_search'),
    path('property/<slug:slug>', views.property_detail_view, name='property_detail'),
]