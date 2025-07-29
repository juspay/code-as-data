{ inputs, ... }:
{
  imports = [ inputs.python-flake.flakeModules.default ];
  perSystem = { pkgs, ... }: {
    python-project = {
      name = "code-as-data";
      pythonVersionFile = true;
      root = ../.;

      overrides = final: prev: {
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
    };
  };
}
