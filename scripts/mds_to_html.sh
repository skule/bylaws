#!/bin/bash
python scripts/mds_to_html.py || exit $?
cp -rf scripts/main.{css,js} scripts/images build/ || exit $?
