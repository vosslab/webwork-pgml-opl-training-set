#!/bin/sh

time python3 -m pg_analyze.main -r problems -o output/

wc -l $(find output/ -type f -name '*.tsv') | sort -n
