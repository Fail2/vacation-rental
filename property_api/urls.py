from django.urls import path
from . import views

app_name = 'property_api'

urlpatterns = [
    path('autocomplete/', views.LocationAutocompleteAPIView.as_view(), name='autocomplete'),
]
