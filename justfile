default:
    @just --list

build-wheel:
  nix build .#wheel

run-service:
  nix run .#code-as-data

test:
  nix run .#test
