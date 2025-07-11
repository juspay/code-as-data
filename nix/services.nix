{ inputs, ... }:
{
  imports = [
    inputs.process-compose-flake.flakeModule
  ];
  perSystem = { ... }:
    {
      process-compose."code-as-data" = {
        imports = [
          inputs.services-flake.processComposeModules.default
        ];

        services.postgres."code-as-data" = {
          enable = true;
          port = 18908; # Picked from .env
          initialScript.after = # sql
            ''
              CREATE ROLE postgres WITH
                LOGIN SUPERUSER CREATEDB
                CREATEROLE REPLICATION BYPASSRLS
                PASSWORD 'postgres';
            '';
          initialDatabases = [
            {
              name = "code_as_data";
            }
          ];
        };
      };
    };
}
