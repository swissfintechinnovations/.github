#!/bin/bash

# Check if the required arguments are provided
if [ $# -ne 2 ]; then
  echo "Usage: $0 <template-filenames> <source-folder>"
  exit 1
fi

# Get the input arguments
TEMPLATE_FILENAMES=$1
SOURCE_FOLDER=$2

# Loop through template filenames and run autoformat_template.js
for file in $(ls "${TEMPLATE_FILENAMES}"); do
  node ../.github/autoformat/autoformat_template.js "$file"
done

# Loop through YAML files in components/parameters and run autoformat_parameter.js
for file in $(find "${SOURCE_FOLDER}/components/parameters" -type f -iname "*.yaml"); do
  node ../.github/autoformat/autoformat_parameter.js "$file"
done

# Loop through YAML files in components/schemas and run autoformat_schema.js
for file in $(find "${SOURCE_FOLDER}/components/schemas" -type f -iname "*.yaml"); do
  node ../.github/autoformat/autoformat_schema.js "$file"
done
