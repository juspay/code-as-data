{
  description = "Code Analysis Repository";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/75a52265bda7fd25e06e3a67dee3f0354e73243c";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs {
          inherit system;
          # Configure substituters explicitly for this flake
          config = {
            substituters = [
              "https://cache.nixos.org/"
            ];
            trusted-public-keys = [
              "cache.nixos.org-1:6NCHdD59X431o0gWypbMrAURkbJ16ZPMQFGspcDShjY="
            ];
          };
        };
        
        # Use Python 3.11
        python = pkgs.python311;
        
        # PostgreSQL configuration
        pgData = "./postgres-data";
        # Use a function to generate a random port between 15000 and 25000
        pgPort = "$(shuf -i 15000-25000 -n 1)";
        pgDbName = "code_as_data";
        pgUsername = "postgres";
        pgPassword = "postgres";
        
      in {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            # Basic Python environment
            python
            python.pkgs.pip
            python.pkgs.setuptools
            python.pkgs.wheel
            
            # Database
            postgresql
            
            # Build dependencies that might be needed for some packages
            gcc
            pkg-config
            openssl.dev
          ];
          
          shellHook = ''
            echo "Entering the development environment for Code Analysis Repository"
            echo "Python version: $(python --version)"
            echo ""
            
            # Set up Python virtual environment if it doesn't exist
            if [ ! -d ".venv" ]; then
              echo "Creating Python virtual environment..."
              python -m venv .venv
            fi
            
            # Activate virtual environment
            source .venv/bin/activate
            
            # Install dependencies if not already installed
            if [ ! -f ".pip-installed" ]; then
              echo "Installing Python dependencies..."
              pip install -r requirements.txt
              touch .pip-installed
            fi
            
            # PostgreSQL service functions
            function start_postgres {
              # Generate a random port number between 15000 and 25000
              local PORT=$(shuf -i 15000-25000 -n 1)
              
              # Create data directory if it doesn't exist
              if [ ! -d "${pgData}" ]; then
                mkdir -p "${pgData}"
                initdb -D "${pgData}" -U ${pgUsername} --auth=trust --no-locale --encoding=UTF8
                
                # Customize postgresql.conf with random port - using port only without comments
                echo "listen_addresses = '*'" > ${pgData}/postgresql.conf.custom
                echo "port = $PORT" >> ${pgData}/postgresql.conf.custom
                cat ${pgData}/postgresql.conf.custom >> ${pgData}/postgresql.conf
                
                # Create authentication config
                echo "local all all trust" > ${pgData}/pg_hba.conf
                echo "host all all 127.0.0.1/32 trust" >> ${pgData}/pg_hba.conf
                echo "host all all ::1/128 trust" >> ${pgData}/pg_hba.conf
              else
                # Get the port from postgresql.conf if it exists
                if grep -q "^port = " ${pgData}/postgresql.conf; then
                  PORT=$(grep "^port = " ${pgData}/postgresql.conf | sed 's/^port = //' | tr -d ' ')
                else
                  # If port is not configured, add it
                  echo "port = $PORT" >> ${pgData}/postgresql.conf
                fi
              fi
              
              # Start PostgreSQL server in background
              pg_ctl -D "${pgData}" -l ${pgData}/postgres.log start
              
              # Wait for PostgreSQL to start
              RETRIES=10
              until pg_isready -h localhost -p $PORT -U ${pgUsername} || [ $RETRIES -eq 0 ]; do
                echo "Waiting for PostgreSQL to start on port $PORT, $RETRIES retries left..."
                RETRIES=$((RETRIES-1))
                sleep 1
              done
              
              # Create database if it doesn't exist
              if ! psql -h localhost -p $PORT -U ${pgUsername} -lqt | cut -d \| -f 1 | grep -qw ${pgDbName}; then
                echo "Creating database ${pgDbName}"
                createdb -h localhost -p $PORT -U ${pgUsername} ${pgDbName}
              else
                echo "Database ${pgDbName} already exists"
              fi
              
              echo "PostgreSQL is running on port $PORT"
              
              # Update .env file with the current port
              if [ -f .env ]; then
                sed -i.bak "s/^DB_PORT=.*/DB_PORT=$PORT/" .env && rm -f .env.bak
              else
                # Create .env file with the current port
                cat > .env << EOF
DB_USER=${pgUsername}
DB_PASSWORD=${pgPassword}
DB_HOST=localhost
DB_PORT=$PORT
DB_NAME=${pgDbName}
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800
EOF
              fi
              
              # Export the port for other functions to use
              export PG_PORT=$PORT
            }
            
            function stop_postgres {
              if [ -n "$PG_PORT" ]; then
                pg_ctl -D "${pgData}" stop
                echo "PostgreSQL server on port $PG_PORT stopped"
              else
                # Try to determine the port from the config file
                if [ -f "${pgData}/postgresql.conf" ] && grep -q "port = " ${pgData}/postgresql.conf; then
                  local PORT=$(grep "port = " ${pgData}/postgresql.conf | sed 's/port = //')
                  pg_ctl -D "${pgData}" stop
                  echo "PostgreSQL server on port $PORT stopped"
                else
                  pg_ctl -D "${pgData}" stop
                  echo "PostgreSQL server stopped"
                fi
              fi
            }
            
            # Create a .env file if it doesn't exist
            # Note: This will be updated with the actual port by the start_postgres function
            if [ ! -f .env ]; then
              echo "Creating initial .env file (port will be updated)"
              cat > .env << EOF
DB_USER=${pgUsername}
DB_PASSWORD=${pgPassword}
DB_HOST=localhost
DB_PORT=0000
DB_NAME=${pgDbName}
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800
EOF
            fi
            
            # Add the project and virtual environment to PATH
            export PATH=$PWD:$PWD/.venv/bin:$PATH
            
            # Register cleanup function to stop PostgreSQL on exit
            trap stop_postgres EXIT
            
            # Start PostgreSQL
            start_postgres
            
            echo ""
            echo "Available commands:"
            echo "  - setup_db.py: Set up the database schema"
            echo "  - import_dumps.py: Import dump files into the database"
            echo "  - query.py: Query the database"
            echo ""
            echo "PostgreSQL service:"
            echo "  - start_postgres: Start the PostgreSQL server"
            echo "  - stop_postgres: Stop the PostgreSQL server"
            echo ""
            echo "Python environment is active. Use pip to manage packages."
          '';
        };
      }
    );
}