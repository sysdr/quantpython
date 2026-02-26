.PHONY: install demo verify stress test clean

install:
	pip install -e ".[dev]"

demo:
	python -m src.demo

verify:
	python -m src.verify

stress:
	python -m src.stress_test

test:
	python -m pytest tests/ -v

clean:
	rm -rf data/asset_registry.json data/verify_registry.json
	rm -rf __pycache__ src/__pycache__ tests/__pycache__
	rm -rf .pytest_cache *.egg-info
