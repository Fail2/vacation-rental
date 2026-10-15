# Vacation Rental Platform

A Django-based vacation rental platform with location autocomplete, property search, and nearby properties using Django GIS and PostgreSQL.

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/Fail2/vacation-rental.git
cd vacation-rental
```

### 2. Install dependencies using uv

```bash
uv sync
```

### 3. Start the database

```bash
docker compose up -d
```

### 4. Run migrations

```bash
uv run python manage.py migrate
```

### 5. Import property data

```bash
uv run python manage.py import_properties data/bd_properties.csv
```

### 6. Start the server

```bash
uv run python manage.py runserver
```

## API Testing

Check the location autocomplete API using `curl`:

```bash
curl "http://127.0.0.1:8000/api/autocomplete/?q=Rang"
```

Check the response with formatted JSON:

```bash
curl -s "http://127.0.0.1:8000/api/autocomplete/?q=Rang" | python3 -m json.tool
```

Replace `Rang` with any location name or prefix to test the autocomplete results.