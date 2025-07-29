#!/bin/bash

# Check if the required arguments are provided
if [ $# -ne 1 ]; then
  echo "Usage: $0 <folder>"
  exit 1
fi

# Get the input arguments
FOLDER=$1
files=( $(find $FOLDER -type f -name "*.yaml") )

total=${#files[@]}

if [ $total -eq 0 ]; then
  echo "No YAML files found in $FOLDER"
  exit 1
fi

# progress bar
print_progress() {
  local current=$1
  local total=$2
  local width=50  # progress bar width in characters

  # Calculate percentage
  local percent=$(( current * 100 / total ))

  # Calculate number of '=' to show
  local progress=$(( current * width / total ))

  # Build the progress bar string
  bar=$(printf '=%.0s' $(seq 1 $width))
  printf "\r[%.*s>%*s] %3d%% (%d/%d) %s\033[K" "$progress" "$bar" $(( width - progress )) "" "$percent" "$current" "$total" "$3"
}

# Loop through template filenames and fix line length
for file in "${files[@]}"; do
  count=$((count + 1))
  # echo -ne "$file \033[K \r"
  print_progress "$count" "$total" "$file"

  node ~/SFTI/.github/.github/autoformat/autoformat_linelength.js "$file"
  # gawk 'BEGIN{RS="\0";ORS=""}{gsub(/\n\n/,"\n");print}' "$file" > tmp && mv tmp "$file" # the bug seems to be fixed
  sed -Ei 's/description: (>|>-|\|-)/description: |/g' "$file"
done

echo ""
echo "Autoformat done."