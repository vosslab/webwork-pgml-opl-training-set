#!/bin/sh

#rm -fr output/
python3 -m pg_analyze.main -r problems -o output/
echo ""
wc -l $(find output/ -type f -name "*.tsv") | sort -n | tail -n 8
echo ""
wc -l $(find output/ -type f -name "*.txt") | sort -n | tail -n 8
echo ""
find output/ -type f -not -name "*.tsv" -not -name "*.txt" | sort -n
#wc -l $(find output/ -type f -not -name "*.tsv" -not -name "*.txt") | sort -n | tail -n 8
