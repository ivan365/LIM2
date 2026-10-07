#!/bin/bash
set -e
export PATH="/Library/TeX/texbin:/usr/local/bin:$PATH"

cd "$(dirname "$0")"

for lang in RU EN UA SK; do
    echo "=================================================="
    echo "Compiling LIM_M2_Datasheet_${lang}.tex..."
    echo "=================================================="
    pdflatex -interaction=nonstopmode "LIM_M2_Datasheet_${lang}.tex"
    pdflatex -interaction=nonstopmode "LIM_M2_Datasheet_${lang}.tex"
done

echo "All datasheets compiled successfully!"
