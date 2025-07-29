{
  perSystem = { self', pkgs, ... }: {
    devShells.default = pkgs.mkShell {
      inputsFrom = [
        self'.devShells.uv2nix
      ];

      packages = [ pkgs.just ];

      DB_HOST = "localhost";
      DB_MAX_OVERFLOW = 20;
      DB_NAME = "code_as_data";
      DB_PASSWORD = "postgres";
      DB_POOL_RECYCLE = 1800;
      DB_POOL_SIZE = 10;
      DB_POOL_TIMEOUT = 30;
      DB_PORT = 18908;
      DB_USER = "postgres";
    };
  };
}
