from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib.gis.db.models.functions import Distance
from .models import Property, Location

def homepage_view(request):
    featured_properties = Property.objects.filter(is_active=True).prefetch_related('images').annotate(
        distance = Distance('point', 'location__point',)
    ).order_by('distance')[:6]
    for property in featured_properties:
        print(property.distance)
    return render(request, 'property_app/homepage.html', {'properties': featured_properties})


def property_search_view(request):
    query = request.GET.get('search', '').strip()

    property_list = Property.objects.filter(is_active=True).select_related('location').prefetch_related('images').all()

    if query:
        print(query)
        property_list = property_list.filter(location__name__icontains=query)

    property_list = property_list.distinct().annotate(
        distance = Distance('point', 'location__point',)
    ).order_by('distance')


    paginator = Paginator(property_list, 6)
    page_number = request.GET.get('page', 1)
    
    try:
        page_obj = paginator.get_page(page_number)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.get_page(1)

    context = {
        'page_obj': page_obj,
        'query': query,
    }
    return render(request, 'property_app/search_results.html', context)


def property_detail_view(request, slug):
    property_queryset = Property.objects.filter(slug=slug).select_related('location')
    
    first_pass = get_object_or_404(property_queryset)
    if first_pass.point and first_pass.location.point:
        property_queryset = property_queryset.annotate(
            distance_from_city=Distance('point', first_pass.location.point)
        )
    
    property_obj = get_object_or_404(property_queryset)
    gallery_images = property_obj.images.all().order_by('sort_order')
    
    distance_km = None
    if hasattr(property_obj, 'distance_from_city') and property_obj.distance_from_city:
        distance_km = round(property_obj.distance_from_city.km, 2)
        
    context = {
        'property': property_obj,
        'gallery_images': gallery_images,
        'distance_km': distance_km,
    }
    return render(request, 'property_app/property_detail.html', context)
