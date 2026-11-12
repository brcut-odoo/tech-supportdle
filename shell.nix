{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShell {
  packages = [
    pkgs.nodejs_22
    (pkgs.python3.withPackages (p: [ p.lxml ]))
  ];
}
