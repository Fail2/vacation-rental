from rest_framework import serializers
from property_app.models import Location

class LocationAutocompleteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Location
        fields = ['id', 'name', 'city', 'country']
