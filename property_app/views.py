from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib.gis.db.models.functions import Distance
from .models import Property, Location

def homepage_view(request):
    featured_properties = Property.objects.filter(is_active=True).prefetch_related('images').annotate(
        distance = Distance('point', 'location__point',)
    ).order_by('distance')[:6]
    
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
    property_obj = get_object_or_404(
        Property.objects.select_related('location'),
        slug=slug
    )

    gallery_images = property_obj.images.all().order_by('sort_order')

    distance_km = None

    if property_obj.point and property_obj.location.point:
        property_obj = Property.objects.filter(
            pk=property_obj.pk
        ).select_related('location').annotate(
            distance_from_city=Distance(
                'point',
                property_obj.location.point
            )
        ).first()

        if property_obj.distance_from_city is not None:
            distance_km = round(
                property_obj.distance_from_city.km,
                2
            )

    nearby_properties = Property.objects.filter(
        is_active=True,
        location_id=property_obj.location_id,
        point__isnull=False
    ).exclude(
        pk=property_obj.pk
    ).select_related(
        'location'
    ).prefetch_related(
        'images'
    )

    if property_obj.point:
        nearby_properties = nearby_properties.annotate(
            distance=Distance(
                'point',
                property_obj.point
            )
        ).order_by('distance')[:6]
    else:
        nearby_properties = nearby_properties.none()

    context = {
        'property': property_obj,
        'gallery_images': gallery_images,
        'distance_km': distance_km,
        'nearby_properties': nearby_properties,
    }

    return render(
        request,
        'property_app/property_detail.html',
        context
    )