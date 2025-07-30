{
  flake.om = {
    develop.default.readme = ''
      `Hint`: Run `just` to see what's available
    '';
    health.default = {
      nix-version.supported = ">=2.16.0";
      caches.required = [ "https://om.cachix.org" ];
      direnv.required = true;
      homebrew = {
        enable = true;
        required = false;
      };
    };
  };
}
