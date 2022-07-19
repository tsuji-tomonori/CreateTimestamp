mkdir -p layer/python
pip install -r requirements.txt -t layer/python
pip list
find layer/python -type f | grep -E "(__pycache__|\.pyc|\.pyo$)" | xargs rm