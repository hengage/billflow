.PHONY: help build up down logs shell db-shell migrate migrations collectstatic

help:
	@echo "Available commands:"
	@echo "  make build     - Build all Docker images (Also starts all services)"
	@echo "  make up        - Start all services"
	@echo "  make down      - Stop and remove all services"
	@echo "  make logs      - Show logs from all services"
	@echo "  make shell     - Open Django shell in web container"
	@echo "  make db-shell  - Open PostgreSQL shell"
	@echo "  make migrations - Create new Django migration files"
	@echo "  make migrate   - Run Django migrations"
	@echo "  make collectstatic - Collect static files"

build:
	docker-compose up --build

up:
	docker-compose up -d

down:
	docker-compose down

logs:
	docker-compose logs -f

shell:
	docker-compose exec web python manage.py shell

db-shell:
	docker-compose exec postgres psql -U postgres -d billflow

migrations:
	docker-compose exec web python manage.py makemigrations

migrate:
	docker-compose exec web python manage.py migrate

collectstatic:
	docker-compose exec web python manage.py collectstatic --noinput

