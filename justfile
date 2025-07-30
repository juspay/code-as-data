# Lists the available Just commands
default:
    @just --list

# Builds the Python package as a wheel
build-wheel:
  nix build .#wheel

# Starts the `code-as-data` service
run-service:
  nix run .#code-as-data

# Run pytest in the environment
test:
  nix run .#test
