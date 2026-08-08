.PHONY: help install install-survival test lint fmt calibrate killtest survival clv figures check clean

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Install the package with dev and viz extras
	pip install -e ".[dev,viz]"

install-survival:  ## Add the Phase 3 baselines (Cox, RSF, and DeepSurv via torch)
	pip install -e ".[dev,viz,survival,deepsurv]"

test:  ## Run the test suite
	pytest tests/ -q

lint:  ## Check formatting and style
	ruff check keel tests

fmt:  ## Auto-fix formatting and style
	ruff check --fix keel tests

calibrate:  ## Verify the simulator against benchmark targets
	@python -c "from keel.sim import simulate,SimConfig; \
	from keel.sim.calibration import check,check_quadrants; \
	r=simulate(SimConfig(4000,24,7)); check(r); print(); check_quadrants(r)"

killtest:  ## Re-run the founding experiment
	@python -c "from keel.sim import simulate,SimConfig; \
	from keel.experiments.kill_test import run; \
	res,po,auc=run(simulate(SimConfig(6000,24,7))); \
	print(f'churn model AUC {auc:.3f}, {len(po)} eligible\n'); \
	[print(f'{r.name:<34}{r.expected_value:>12,.0f}') for r in res]"

survival:  ## Phase 3 head-to-head vs Cox / RSF / DeepSurv (needs the survival extras)
	@python -m keel.experiments.survival_benchmark

clv:  ## Value every simulated customer and split the leak by cause
	@python -m keel.experiments.clv

figures:  ## Regenerate figures (also syncs the explainer copy)
	@python -m keel.experiments.figures
	@python -m keel.experiments.survival_figures
	@cp papers/figures/*.png explainer/figures/
	@echo "figures regenerated and synced to explainer/figures/"

check: lint test calibrate  ## Everything CI runs, locally

clean:  ## Remove caches and build artifacts
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache build dist *.egg-info
