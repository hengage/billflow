.PHONY: help build up down logs shell db-shell migrate migrations collectstatic create-app

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
	@echo "  make add-dep NAME=<package> - Install new Python package in container, then freeze"
	@echo "  make create-app NAME=<app_name> - Create new Django app in apps directory"

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

add-dep:
ifndef NAME
	$(error NAME is undefined. Usage: make add-dep NAME=<package>)
endif
	docker-compose exec web pip install $(NAME)
	docker-compose exec web pip freeze > requirements.txt

create-app:
ifndef NAME
	$(error NAME is undefined. Usage: make create-app NAME=<app_name>)
endif
	docker-compose exec web bash -c "mkdir -p apps/$(NAME) && touch apps/$(NAME)/__init__.py apps/$(NAME)/apps.py apps/$(NAME)/models.py apps/$(NAME)/serializers.py apps/$(NAME)/views.py apps/$(NAME)/urls.py apps/$(NAME)/permissions.py apps/$(NAME)/admin.py" apps/$(NAME)/migrations/__init__.py