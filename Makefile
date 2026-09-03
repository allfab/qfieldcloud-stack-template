# Toutes les commandes Compose se lancent depuis src/ : voir l'article precedent.
COMPOSE = cd src && docker compose --env-file ../.env

up:      ; $(COMPOSE) up -d --build
down:    ; $(COMPOSE) down
config:  ; $(COMPOSE) config -q
ps:      ; $(COMPOSE) ps
logs:    ; $(COMPOSE) logs -f $(S)
migrate: ; $(COMPOSE) exec app python manage.py migrate
