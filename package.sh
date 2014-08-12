#!/usr/bin/env bash

set -e

rm plugin.video.vimeo.zip
cp -r plugin plugin.video.vimeo
zip -r plugin.video.vimeo.zip plugin.video.vimeo
rm -rf ./plugin.video.vimeo
