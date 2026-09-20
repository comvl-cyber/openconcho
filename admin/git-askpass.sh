#!/bin/sh
case "$1" in
  *Username*) printf '%s\n' "comvl-cyber" ;;
  *Password*) printf '%s\n' "$GITHUB_TOKEN" ;;
  *) exit 1 ;;
esac
