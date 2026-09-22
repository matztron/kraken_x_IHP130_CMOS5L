# Repo-root wrappers. The suite lives in test/.
.PHONY: help test test-assemble test-sim clean venv

help test test-assemble test-sim clean:
	$(MAKE) -C test $@ TEST="$(TEST)"

venv:
	python3.13 -m venv .venv
	.venv/bin/pip install -r requirements.txt
