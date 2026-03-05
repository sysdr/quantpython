#!/usr/bin/env bash
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -name '*.pyc' -delete
echo 'Cleaned.'
