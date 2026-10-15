from rest_framework.views import APIView
from rest_framework.response import Response
from pgvector.django import CosineDistance
from property_app.models import Location
from .serializers import LocationAutocompleteSerializer
from property_app.embedding import text_embed

class LocationAutocompleteAPIView(APIView):
    def get(self, request, *args, **kwargs):
        query = request.GET.get('q', '').strip()
        if not query or len(query) < 2:
            return Response({'message': 'The location name at least 2 letters'})
        
        query_vector = text_embed(query)
        
        locations = Location.objects.filter(is_active=True).annotate(
            distance=CosineDistance('embedding', query_vector)
        ).filter(distance__lte=0.9).order_by('distance')[:6]
        
        serializer = LocationAutocompleteSerializer(locations, many=True)
        return Response(serializer.data)
