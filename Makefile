.PHONY: setup run test verify clean

setup:
	pip install -r requirements.txt

run:
	python -m service.app

test:
	pytest tests/ -v

verify:
	python3 verify.py

clean:
	rm -f jobs.db
