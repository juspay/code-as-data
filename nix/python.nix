# NOTE: This module is temporary. It will soon be upstreamed to a dedicated flake-parts module,
# and replaced with a minimal Nix file, similar to how haskell-flake is used in other repositories.
# For progress and discussion, see: https://github.com/juspay/python-nix-template/issues/2
{ inputs, ... }:
let
  inherit (inputs) uv2nix pyproject-nix pyproject-build-systems;
in
{
  perSystem = { self', config, pkgs, ... }:
    let
      inherit (pkgs) lib;
      root = ./../.;
      pythonVersionFile = "${root}/.python-version";

      versionStr =
        with builtins;
        with lib;
        let
          raw = if pathExists pythonVersionFile then readFile pythonVersionFile else "";
          m = match "([0-9]+)\\.([0-9]+).*" (removeSuffix "\n" raw); # ["3" "13"]
        in
        if m != null && m != [ ] then concatStringsSep "" m else "311";

      python = pkgs."python${versionStr}";

      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = root; };

      overlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };

      editableOverlay = workspace.mkEditablePyprojectOverlay { root = "$REPO_ROOT"; };
      pyprojectOverrides = final: prev: {
        psycopg2-binary = prev.psycopg2-binary.overrideAttrs (old: {
          buildInputs = (old.buildInputs or [ ]) ++ [
            pkgs.postgresql.pg_config
            pkgs.postgresql.dev
            pkgs.openssl.dev
          ];
          nativeBuildInputs = (old.nativeBuildInputs or [ ]) ++ [
            pkgs.postgresql.dev
            (final.resolveBuildSystem {
              setuptools = [ ];
            })
          ];
        });
      };

      pythonSet =
        ((pkgs.callPackage pyproject-nix.build.packages {
          inherit python;
        }).overrideScope
          (
            lib.composeManyExtensions [
              pyproject-build-systems.overlays.default
              pyprojectOverrides
              overlay
            ]
          )).pythonPkgsHostHost.overrideScope pyprojectOverrides;

      # reuquired to create editable venv
      editablePythonSet = pythonSet.overrideScope (
        lib.composeManyExtensions [
          editableOverlay
          (final: prev: {
            code-as-data = prev.code-as-data.overrideAttrs (old: {
              src = lib.fileset.toSource {
                root = old.src;
                fileset = lib.fileset.unions [
                  (old.src + "/pyproject.toml")
                  (old.src + "/README.md")
                  (old.src + "/code_as_data")
                  (old.src + "/tests")
                ];
              };
              nativeBuildInputs =
                old.nativeBuildInputs
                ++ final.resolveBuildSystem {
                  editables = [ ];
                };
            });
          })
        ]
      );
      venv = editablePythonSet.mkVirtualEnv "code-as-data" workspace.deps.all;
    in
    {
      packages = {
        default = pythonSet.mkVirtualEnv "code-as-data" workspace.deps.all;
        wheel = pythonSet.code-as-data.override {
          pyprojectHook = pythonSet.pyprojectDistHook;
        };
      };

      apps.test.program = "${lib.getExe' self'.packages.default "pytest"}";

      devShells = {
        uv2nix = pkgs.mkShell {
          inputsFrom = [
            config.pre-commit.devShell
          ];
          packages = [
            venv
            pkgs.uv
          ];
          env = {
            UV_NO_SYNC = "1";
            UV_PYTHON = "${lib.getExe' venv "python"}";
            UV_PYTHON_DOWNLOADS = "never";
          };

          shellHook = # sh
            ''
              # Undo dependency propagation by nixpkgs.
              unset PYTHONPATH

              # Get repository root using git. This is expanded at runtime by the editable `.pth` machinery.
              export REPO_ROOT=$(git rev-parse --show-toplevel)

              echo "Entering the development environment for Code Analysis Repository"
              echo "Python version: $(python --version)"
              echo ""
            '';
        };
      };
    };
}
