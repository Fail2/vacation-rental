
import hashlib
import json
import logging
import re
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import pandas as pd
from PIL import Image as PILImage

from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.text import slugify

from property_app.models import Location, Property, PropertyImage


logger = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15 MB


REQUIRED_COLUMNS = [
    "id",
    "country",
    "state",
    "city",
    "display",
    "location_id",
    "property_name",
    "property_slug",
    "property_type_category",
    "usd_price",
    "bedroom_count",
    "bathroom_count",
    "published",
    "images",
    "location_lonlat",
    "property_lonlat",
    "location_boundary_geojson",
    "property_footprint_geojson",
    "property_status",
]


def text(value, default=""):
    if pd.isna(value):
        return default

    value = str(value).strip()

    if value.lower() in {"", "nan", "none", "null"}:
        return default

    return value


def parse_bool(value, default=False):
    value = text(value).lower()

    if value in {"true", "1", "yes"}:
        return True

    if value in {"false", "0", "no"}:
        return False

    if not value:
        return default

    raise ValueError(f"Invalid boolean value: {value!r}")


def parse_decimal(value, field_name, default="0"):
    value = text(value, default)

    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(
            f"{field_name} is not a valid number: {value!r}"
        ) from exc

    if not number.is_finite() or number < 0:
        raise ValueError(
            f"{field_name} must be a finite non-negative number."
        )

    return number


def parse_integer(value, field_name, default=0):
    number = parse_decimal(value, field_name, str(default))

    if number != number.to_integral_value():
        raise ValueError(f"{field_name} must be a whole number.")

    result = int(number)

    if result > 32767:
        raise ValueError(f"{field_name} exceeds PositiveSmallIntegerField.")

    return result


def parse_geojson(value, expected_type):
    raw = text(value)

    if not raw:
        return None

    try:
        data = json.loads(raw)

        # Support the CSV's lonlat structure:
        # {"coordinates": [longitude, latitude]}
        if isinstance(data, dict) and "type" not in data:
            coordinates = data.get("coordinates")

            if not isinstance(coordinates, list) or len(coordinates) != 2:
                raise ValueError("Invalid longitude/latitude coordinates.")

            lon, lat = coordinates

            if not (-180 <= float(lon) <= 180):
                raise ValueError("Longitude is outside valid range.")

            if not (-90 <= float(lat) <= 90):
                raise ValueError("Latitude is outside valid range.")

            data = {
                "type": "Point",
                "coordinates": [float(lon), float(lat)],
            }

        if data.get("type") == "Feature":
            data = data.get("geometry")

        if not data:
            raise ValueError("GeoJSON geometry is missing.")

        geom = GEOSGeometry(json.dumps(data), srid=4326)

        if geom.empty:
            raise ValueError("Geometry is empty.")

        # Location.boundary is MultiPolygonField.
        if expected_type == "MultiPolygon" and geom.geom_type == "Polygon":
            geom = MultiPolygon(geom, srid=4326)

        # Property.footprint is PolygonField, so a multi-part footprint
        # cannot be stored directly in this model.
        if expected_type == "Polygon" and geom.geom_type == "MultiPolygon":
            if len(geom) != 1:
                raise ValueError(
                    "Footprint is MultiPolygon but Property.footprint "
                    "accepts only Polygon. Update the model if multipart "
                    "footprints must be supported."
                )
            geom = geom[0]

        if geom.geom_type != expected_type:
            raise ValueError(
                f"Expected {expected_type}, got {geom.geom_type}."
            )

        if not geom.valid:
            raise ValueError("Geometry is invalid.")

        return geom

    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid {expected_type} GeoJSON: {exc}") from exc


def safe_slug(value, max_length=50):
    base = slugify(value) or "item"

    if len(base) <= max_length:
        return base

    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]
    return f"{base[:max_length - 9].rstrip('-')}-{digest}"


def parse_image_urls(value):
    raw = text(value)

    if not raw:
        return []

    try:
        urls = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid images JSON: {exc}") from exc

    if not isinstance(urls, list):
        raise ValueError("'images' must contain a JSON array.")

    result = []

    for url in urls:
        if not isinstance(url, str):
            continue

        url = url.strip()
        parsed = urlparse(url)

        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            logger.warning("Skipping invalid image URL: %r", url)
            continue

        result.append(url)

    return result


def download_image(url):
    """
    Download and validate an image before saving it to ImageField storage.
    Only use trusted CSV files and trusted image hosts.
    """
    request = Request(
        url,
        headers={"User-Agent": "DjangoPropertyImporter/1.0"},
    )

    with urlopen(request, timeout=15) as response:
        content_type = response.headers.get("Content-Type", "").lower()
        data = response.read(MAX_IMAGE_BYTES + 1)

    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Image exceeds 15 MB limit.")

    if not content_type.startswith("image/"):
        raise ValueError(
            f"URL did not return an image: {content_type!r}"
        )

    with PILImage.open(BytesIO(data)) as image:
        image.verify()

    with PILImage.open(BytesIO(data)) as image:
        width, height = image.size
        image_format = (image.format or "").upper()

    extensions = {
        "JPEG": ".jpg",
        "PNG": ".png",
        "WEBP": ".webp",
        "GIF": ".gif",
        "TIFF": ".tiff",
        "BMP": ".bmp",
    }

    extension = extensions.get(image_format)

    if not extension:
        raise ValueError(f"Unsupported image format: {image_format}")

    return data, width, height, extension


class Command(BaseCommand):
    help = "Import locations, properties and property images from CSV."

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate CSV without saving records or downloading images.",
        )
        parser.add_argument(
            "--skip-images",
            action="store_true",
            help="Do not download images.",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["csv_file"])

        if not csv_path.is_file():
            raise CommandError(f"CSV file not found: {csv_path}")

        try:
            df = pd.read_csv(csv_path, dtype=str, keep_default_na=True)
        except Exception as exc:
            raise CommandError(f"Could not read CSV: {exc}") from exc

        missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]

        if missing:
            raise CommandError(
                "CSV is missing required columns: " + ", ".join(missing)
            )

        success_count = 0
        failed_count = 0
        image_count = 0

        for index, row in df.iterrows():
            csv_row = index + 2
            source_id = text(row.get("id"), f"row-{csv_row}")

            try:
                country = text(row["country"])
                state = text(row["state"])
                city = text(row["city"])
                display = text(row["display"])

                title = text(row["property_name"])
                property_type = text(row["property_type_category"])
                status = text(row["property_status"], "draft")

                if not all([country, city, display, title, property_type]):
                    raise ValueError(
                        "country, city, display, property name and "
                        "property type are required."
                    )

                price = parse_decimal(row["usd_price"], "usd_price")
                bedrooms = parse_integer(row["bedroom_count"], "bedroom_count")
                bathrooms = parse_integer(row["bathroom_count"], "bathroom_count")
                published = parse_bool(row["published"], default=False)

                location_id = text(row["location_id"])
                location_slug = safe_slug(
                    f"{country}-{city}-{location_id}"
                )

                property_slug = text(row["property_slug"])
                if not property_slug:
                    property_slug = safe_slug(f"{title}-{source_id}")

                property_slug = safe_slug(
                    property_slug,
                    Property._meta.get_field("slug").max_length,
                )

                location_point = parse_geojson(
                    row.get("location_lonlat"), "Point"
                )
                property_point = parse_geojson(
                    row.get("property_lonlat"), "Point"
                )
                location_boundary = parse_geojson(
                    row.get("location_boundary_geojson"), "MultiPolygon"
                )
                property_footprint = parse_geojson(
                    row.get("property_footprint_geojson"), "Polygon"
                )

                image_urls = parse_image_urls(row.get("images"))

                if options["dry_run"]:
                    success_count += 1
                    continue

                with transaction.atomic():
                    location, _ = Location.objects.update_or_create(
                        slug=location_slug,
                        defaults={
                            "name": display,
                            "country": country,
                            "state": "" if state.lower() == "null" else state,
                            "city": city,
                            "address": display,
                            "point": location_point,
                            "boundary": location_boundary,
                            "is_active": True,
                        },
                    )

                    property_obj, _ = Property.objects.update_or_create(
                        slug=property_slug,
                        defaults={
                            "location": location,
                            "title": title,
                            "description": (
                                f"Imported listing {source_id}. "
                                "Verify listing details with the original source."
                            ),
                            "property_type": property_type,
                            "status": status,
                            "price": price,
                            "bedrooms": bedrooms,
                            "bathrooms": bathrooms,
                            "area_sqft": None,
                            "address": display,
                            "point": property_point,
                            "footprint": property_footprint,
                            "is_featured": False,
                            "is_active": published,
                        },
                    )

                    # The model stores files, not remote URLs.
                    # Do not duplicate image records on repeated imports.
                    if not options["skip_images"] and not property_obj.images.exists():
                        for sort_order, url in enumerate(image_urls):
                            try:
                                data, width, height, extension = download_image(url)

                                filename = (
                                    f"{property_slug}-{sort_order + 1}{extension}"
                                )

                                image_obj = PropertyImage(
                                    property=property_obj,
                                    alt_text=f"{title} - image {sort_order + 1}",
                                    caption=f"Imported image for {title}",
                                    width=width,
                                    height=height,
                                    file_size=len(data),
                                    is_primary=(sort_order == 0),
                                    sort_order=sort_order,
                                )

                                image_obj.image.save(
                                    filename,
                                    ContentFile(data),
                                    save=True,
                                )

                                image_count += 1

                            except Exception as image_exc:
                                logger.warning(
                                    "Image failed for CSV row %s, URL %s: %s",
                                    csv_row,
                                    url,
                                    image_exc,
                                )
                                self.stderr.write(
                                    self.style.WARNING(
                                        f"Row {csv_row}: image skipped: {image_exc}"
                                    )
                                )

                success_count += 1

            except Exception as exc:
                failed_count += 1
                logger.exception(
                    "Failed importing CSV row %s (id=%s)",
                    csv_row,
                    source_id,
                )
                self.stderr.write(
                    self.style.ERROR(
                        f"CSV row {csv_row} (id={source_id}): "
                        f"{type(exc).__name__}: {exc}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported/validated: {success_count}; "
                f"failed rows: {failed_count}; "
                f"images saved: {image_count}; "
                f"dry-run: {options['dry_run']}"
            )
        )