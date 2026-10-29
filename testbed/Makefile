# SKAVA testbed. `make data up seed` brings up a populated four-node federation.
PROFILE ?= ci
PY ?= ../.venv/bin/python
# A Python with matplotlib, for the figures.
PLOT_PY ?= ../../VisIVO-next/backend/.venv/bin/python
BENCH_DB ?= postgresql+psycopg://skava:skava@localhost:$${TESTBED_DB_PORT:-15432}/skava_bench
VISIVO_REPO ?= ../../VisIVO-next
COMPOSE = docker compose -f docker-compose.yml
# The catalogues' web admin (/admin/): a local account, created by `make admin`.
TESTBED_ADMIN_USER ?= admin
TESTBED_ADMIN_PASSWORD ?= TestbedAdmin1

SERVICES = db keycloak skava skava-2 broker node-big node-small node-far node-busy

.PHONY: data node-base db-ready up seed admin status down clean experiments experiment-e1 experiment-e6 conformance figures tables

data:            ## generate the science data (PROFILE=ci|paper)
	$(PY) make_data.py --profile $(PROFILE)

node-base:       ## the VisIVO backend image the nodes are built on (from the VisIVO repository)
	docker build -f $(VISIVO_REPO)/benchmark/remote/Dockerfile -t skava-testbed-node-base $(VISIVO_REPO)

db-ready:        ## the catalogue databases (the second site's is made on an existing volume too)
	$(COMPOSE) up -d --wait db
	$(COMPOSE) exec -T db psql -U skava -d skava -tc "SELECT 1 FROM pg_database WHERE datname='skava2'" | grep -q 1 \
	    || $(COMPOSE) exec -T db psql -U skava -d skava -c "CREATE DATABASE skava2 OWNER skava"

up: node-base db-ready    ## build and start the two catalogues, the IAM, the broker and the nodes
	$(COMPOSE) up -d --build --wait $(SERVICES)

seed:            ## register the nodes, then publish each node's holdings in place (the second site: far and busy)
	$(COMPOSE) exec -T skava python /testbed/seed_nodes.py
	$(COMPOSE) exec -T -e SEED_NODES=FAR,BUSY skava-2 python /testbed/seed_nodes.py
	for n in big small far busy far-2 busy-2; do $(COMPOSE) run --rm publisher-$$n || exit 1; done

admin:           ## an admin account on both catalogues' web admin (http://localhost:18000/admin/ and :18001)
	for s in skava skava-2; do $(COMPOSE) exec -T $$s python -m app.admin.cli create-user --username '$(TESTBED_ADMIN_USER)' --role admin --password '$(TESTBED_ADMIN_PASSWORD)' || exit 1; done

status:          ## what the catalogues and the broker know
	curl -s http://localhost:18000/availability?include_nodes=true; echo
	curl -s http://localhost:18001/availability?include_nodes=true; echo
	curl -s http://localhost:18200/v1/info; echo

down:            ## stop and remove the containers and the catalogue
	$(COMPOSE) --profile seed down -v

clean: down      ## also remove the generated data
	rm -rf data results

experiments:     ## E2..E6 against the running testbed (results/*.json|csv)
	$(PY) -m experiments.e2_placement
	$(PY) -m experiments.e3_failure
	$(PY) -m experiments.e4_bytes
	$(PY) -m experiments.e5_finder
	$(PY) -m experiments.e6_federation

experiment-e6:   ## federation: the two catalogues merged, the IAM's tokens, a site down
	$(PY) -m experiments.e6_federation

conformance:     ## pyvo against the catalogue's TAP and DataLink and a node's SODA, from inside the testbed network (log: results/conformance.log)
	@out=results/conformance.log; rc=0; \
	head="# $$(date -u +%Y-%m-%dT%H:%M:%SZ) SKAVA $$(git -C .. describe --tags --always --dirty) ($$(git -C .. rev-parse --short HEAD))"; \
	head="$$head VisIVO $$(git -C $(VISIVO_REPO) describe --tags --always --dirty) ($$(git -C $(VISIVO_REPO) rev-parse --short HEAD))"; \
	changed="$$(git -C .. status --porcelain | grep -v 'testbed/results/conformance.log' | sed 's/^/# SKAVA changed: /')"; \
	changed="$$changed$$(git -C $(VISIVO_REPO) status --porcelain | sed 's/^/# VisIVO changed: /')"; \
	{ echo "$$head"; [ -z "$$changed" ] || echo "$$changed"; } > $$out; \
	docker run --rm --network $${TESTBED_NETWORK:-testbed_default} -v $(abspath conformance):/conformance:ro \
	    -e TESTBED_BACKEND_TOKEN=$${TESTBED_BACKEND_TOKEN:-testbed-backend-token} \
	    skava-testbed-node python /conformance/check_pyvo.py >> $$out 2>&1 || rc=$$?; \
	cat $$out; exit $$rc

experiment-e1:   ## the routing benchmark on the testbed's PostgreSQL (a separate database)
	$(COMPOSE) exec -T db psql -U skava -d skava -tc "SELECT 1 FROM pg_database WHERE datname='skava_bench'" | grep -q 1 \
	    || $(COMPOSE) exec -T db psql -U skava -d skava -c "CREATE DATABASE skava_bench"
	cd .. && $(abspath $(PY)) scripts/benchmark_routing.py --database-url "$(BENCH_DB)" --n 10000 100000 1000000 --k 3 --out testbed/results/routing_n
	cd .. && $(abspath $(PY)) scripts/benchmark_routing.py --database-url "$(BENCH_DB)" --n 10000 --k 1 3 10 30 --out testbed/results/routing_k
	$(PY) -m experiments.e1_prober

figures:         ## results/figures/*.pdf from the results
	$(PLOT_PY) -m experiments.plots

tables:          ## results/tables/*.tex (the paper's tables) from the results
	$(PY) -m experiments.tables
