# MyClinic API

A Django REST Framework starter project for the MyClinic API.

## Requirements

- Python 3.10 or newer

## Setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

The API health endpoint is available at `http://127.0.0.1:8000/api/health/`.

## Tests

```powershell
python manage.py test
```
