{ inputs, ... }:
{
  perSystem = { self', pkgs, ... }:
    let
      envFile = builtins.readFile (inputs.self + /.env);
      rawLines = builtins.split "\n" envFile;

      # Pre-filter to only valid env lines
      envLines = builtins.filter
        (line:
          builtins.isString line &&
          line != "" &&
          !(builtins.match "^[ \t]*#.*" line != null) && # Not a comment
          (builtins.match ".*=.*" line != null)            # Contains =
        )
        rawLines;
      envVars = builtins.listToAttrs (map
        (line:
          let
            parts = builtins.split "=" line;
            key = builtins.elemAt parts 0;
            value = builtins.elemAt parts 2;
          in
          { name = key; value = value; })
        envLines);
    in
    {
      devShells.default = (pkgs.mkShell envVars // {
        importsFrom = [
          self'.devShells.uv2nix
        ];

        shellHook = ''
          echo "Welcome to the Code as Data development shell!"
        '';
      });
    };
}
