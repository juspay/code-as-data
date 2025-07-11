{
  description = "Flake for juspay/code-as-data";

  inputs = {
    flake-parts.url = "github:hercules-ci/flake-parts";
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    systems.url = "github:nix-systems/default";

    git-hooks.url = "github:cachix/git-hooks.nix";
    git-hooks.flake = false;

    process-compose-flake.url = "github:Platonic-Systems/process-compose-flake";
    services-flake.url = "github:juspay/services-flake";

    pyproject-nix.url = "github:pyproject-nix/pyproject.nix";
    pyproject-nix.inputs.nixpkgs.follows = "nixpkgs";

    uv2nix.url = "github:pyproject-nix/uv2nix";
    uv2nix.inputs.pyproject-nix.follows = "pyproject-nix";
    uv2nix.inputs.nixpkgs.follows = "nixpkgs";

    pyproject-build-systems.url = "github:pyproject-nix/build-system-pkgs";
    pyproject-build-systems.inputs.pyproject-nix.follows = "pyproject-nix";
    pyproject-build-systems.inputs.uv2nix.follows = "uv2nix";
    pyproject-build-systems.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = inputs@{ flake-parts, ... }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      debug = true;
      systems = import inputs.systems;
      imports = with builtins; map (fn: ./nix/${fn}) (attrNames (readDir ./nix));
    };
}
