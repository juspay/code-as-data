{ inputs, ... }:
{
  imports = [
    inputs.process-compose-flake.flakeModule
  ];
  perSystem = { config, ... }:
    {
      process-compose."code-as-data" = {
        imports = [
          inputs.services-flake.processComposeModules.default
        ];

        services.postgres."code-as-data" = {
          enable = true;
          port = config.devShells.default.DB_PORT;
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
