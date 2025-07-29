repos=("ca-payment" "ca-card" "ca-mortgage" "ca-pension")
#repos=("ca-payment" "ca-card" "ca-mortgage")

for repo in "${repos[@]}"; do
  cd ~/SFTI/${repo}/src/components/schemas/generic/

  for file in *.yaml; do
    cp $file ~/SFTI/.github/components/schemas/generic/${file%.yaml}.${repo}.yaml
  done
done