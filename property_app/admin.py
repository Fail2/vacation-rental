from django.contrib import admin
from django.utils.safestring import mark_safe
from django.contrib.gis.admin import GISModelAdmin
from django import forms
from django.core.exceptions import ValidationError
from property_app.models import Location, Property, PropertyImage
# Register your models here.

@admin.register(Location)
class LocationAdmin(GISModelAdmin):
    list_display = ('name', 'city', 'country', 'is_active')
    list_filter = ('country', 'city', 'is_active')
    search_fields = ('name', 'city', 'state', 'country')
    prepopulated_fields = {'slug': ('name',)}

class PropertyImageInlineFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()

        primary_count = 0
        image_count = 0

        for form in self.forms:
            if not form.is_valid():
                continue

            cleaned_data = form.cleaned_data

            if cleaned_data.get("DELETE", False):
                continue

            if not form.instance.pk and not cleaned_data.get("image"):
                continue

            image_count += 1

            if cleaned_data.get("is_primary"):
                primary_count += 1

        if image_count == 0:
            return

        if primary_count > 1:
            raise ValidationError(
                "You can't mark multiple images as the primary image. "
                "Please select only one."
            )

        if primary_count < 1:
            raise ValidationError(
                "Please select one primary image."
            )

class PropertyImageInline(admin.TabularInline):
    model = PropertyImage
    formset = PropertyImageInlineFormSet
    extra = 1
    fields = ('image', 'image_preview_field', 'alt_text', 'caption', 'is_primary', 'sort_order')
    readonly_fields = ('image_preview_field',)

    def image_preview_field(self, obj):
        if obj.image:
            return mark_safe(f'<img src="{obj.image.url}" style="max-height: 100px; width: auto; border-radius: 4px;" />')
        return 'No image uploaded yet'
    image_preview_field.short_description = 'Image Preview'

@admin.register(Property)
class PropertyAdmin(GISModelAdmin):
    list_display = ('title', 'location', 'property_type', 'price', 'is_featured', 'is_active')
    list_filter = ('property_type', 'status', 'is_featured', 'is_active', 'location__city')
    search_fields = ('title', 'description', 'address')
    prepopulated_fields = {'slug': ('title',)}

    inlines = [PropertyImageInline]