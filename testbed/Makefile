# SKAVA testbed. `make data up seed` brings up a populated four-node federation.
PROFILE ?= ci
PY ?= ../.venv/bin/python
COMPOSE = docker compose -f docker-compose.yml

.PHONY: data up seed status down clean

data:            ## generate the science data (PROFILE=ci|paper)
	$(PY) make_data.py --profile $(PROFILE)

up:              ## build and start catalogue + nodes
	$(COMPOSE) up -d --build --wait db skava node-big node-small node-far node-busy

seed:            ## register the nodes, then publish each node's holdings in place
	$(COMPOSE) exec -T skava python /testbed/seed_nodes.py
	for n in big small far busy; do $(COMPOSE) run --rm publisher-$$n || exit 1; done

status:          ## what SKAVA knows
	curl -s http://localhost:18000/availability?include_nodes=true; echo

down:            ## stop and remove the containers and the catalogue
	$(COMPOSE) --profile seed down -v

clean: down      ## also remove the generated data
	rm -rf data results
