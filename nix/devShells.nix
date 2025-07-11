{
  perSystem = { self', pkgs, ... }: {
    devShells.default = pkgs.mkShell {
      importsFrom = [
        self'.devShells.uv2nix
      ];
      shellHook = ''
        echo "Welcome to the Code as Data development shell!"
      '';
    };
  };
}
